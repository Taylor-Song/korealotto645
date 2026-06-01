import os
import json
import requests
import datetime
import time
from enum import Enum

DATA_FILE = "data/draws_delta.json"
BASE_DRAW_NO = 1204
API_URL = "https://www.dhlottery.co.kr/common.do"

class FetchResult(Enum):
    SUCCESS = 1
    UNAVAILABLE = 2
    INVALID_RESPONSE = 3
    NETWORK_ERROR = 4

def fetch_draw_data(draw_no):
    """Fetches draw data from DHLottery API with robust diagnostics."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.dhlottery.co.kr/gameResult.do?method=byWin",
        "X-Requested-With": "XMLHttpRequest",
        "Connection": "close"
    }
    params = {
        "method": "getLottoNumber",
        "drwNo": draw_no
    }

    try:
        response = requests.get(API_URL, params=params, headers=headers, timeout=15)
        status_code = response.status_code
        content_type = response.headers.get('Content-Type', 'unknown')
        final_url = response.url
        text = response.text or ""
        
        # Log basic diagnostics for every request
        print(f"fetch {draw_no}: status={status_code}, content-type={content_type}, url={final_url}")

        if status_code != 200:
            preview = repr(text[:200])
            print(f"::warning::HTTP Error for draw {draw_no}: status={status_code}, preview={preview}")
            return FetchResult.INVALID_RESPONSE, None

        # Try to parse JSON
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as e:
            preview = repr(text[:500])
            print(f"::warning::Non-JSON response for draw {draw_no}: status={status_code}, content-type={content_type}, error={e}")
            print(f"Response preview: {preview}")
            return FetchResult.INVALID_RESPONSE, None
        
        if data.get("returnValue") == "success":
            draw_info = {
                "drawNo": int(data["drwNo"]),
                "drawDate": data["drwNoDate"],
                "numbers": [
                    int(data["drwtNo1"]),
                    int(data["drwtNo2"]),
                    int(data["drwtNo3"]),
                    int(data["drwtNo4"]),
                    int(data["drwtNo5"]),
                    int(data["drwtNo6"])
                ],
                "bonusNumber": int(data["bnusNo"]),
                "firstWinnerCount": int(data["firstPrzwnerCo"]),
                "firstPrizeAmount": int(data["firstWinPrizamnt"]),
                "totalSellAmount": int(data["totSellamnt"])
            }
            return FetchResult.SUCCESS, draw_info
        else:
            print(f"Draw {draw_no} not available yet (returnValue: {data.get('returnValue')})")
            return FetchResult.UNAVAILABLE, None

    except requests.exceptions.RequestException as e:
        print(f"::warning::Network error fetching draw {draw_no}: {e}")
        return FetchResult.NETWORK_ERROR, None

def main():
    # Load existing data
    if not os.path.exists(DATA_FILE):
        print(f"File {DATA_FILE} not found. Creating initial structure.")
        feed_data = {
            "schemaVersion": 1,
            "baseDrawNo": BASE_DRAW_NO,
            "updatedAt": datetime.datetime.utcnow().isoformat() + "Z",
            "latestDrawNo": BASE_DRAW_NO,
            "draws": []
        }
    else:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            feed_data = json.load(f)

    # Determine start point
    current_latest = feed_data.get("latestDrawNo", BASE_DRAW_NO)
    if not feed_data["draws"]:
        start_draw = BASE_DRAW_NO + 1
    else:
        start_draw = max(draw["drawNo"] for draw in feed_data["draws"]) + 1
    
    start_draw = max(start_draw, current_latest + 1)
    
    print(f"Starting fetch from draw {start_draw}...")
    
    stats = {
        "attempted": 0,
        "success": 0,
        "unavailable": 0,
        "network_error": 0,
        "invalid_response": 0,
        "added": 0
    }
    
    consecutive_unavailable = 0
    consecutive_errors = 0
    MAX_CONSECUTIVE_UNAVAILABLE = 3
    MAX_CONSECUTIVE_ERRORS = 2
    
    target_draw = start_draw
    while True:
        stats["attempted"] += 1
        result, draw_info = fetch_draw_data(target_draw)
        
        if result == FetchResult.SUCCESS:
            feed_data["draws"].append(draw_info)
            feed_data["latestDrawNo"] = draw_info["drawNo"]
            stats["success"] += 1
            stats["added"] += 1
            consecutive_unavailable = 0
            consecutive_errors = 0
            print(f"Added draw {target_draw}: {draw_info['drawDate']}")
        elif result == FetchResult.UNAVAILABLE:
            stats["unavailable"] += 1
            consecutive_unavailable += 1
            consecutive_errors = 0
            if consecutive_unavailable >= MAX_CONSECUTIVE_UNAVAILABLE:
                print(f"Stopped after {consecutive_unavailable} consecutive unavailable draws.")
                break
        elif result == FetchResult.INVALID_RESPONSE:
            stats["invalid_response"] += 1
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"::error::Stopped after {consecutive_errors} consecutive invalid responses.")
                break
        elif result == FetchResult.NETWORK_ERROR:
            stats["network_error"] += 1
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"::error::Stopped after {consecutive_errors} consecutive network errors.")
                break
        
        target_draw += 1
        time.sleep(1.5) # Be gentle to the server

    print("\nSummary:")
    for key, value in stats.items():
        print(f"- {key}: {value}")

    if stats["added"] > 0:
        feed_data["draws"].sort(key=lambda x: x["drawNo"])
        feed_data["updatedAt"] = datetime.datetime.utcnow().isoformat() + "Z"
        
        temp_file = DATA_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(feed_data, f, ensure_ascii=False, indent=2)
        
        os.replace(temp_file, DATA_FILE)
        print(f"\nSuccessfully updated {DATA_FILE} with {stats['added']} new draws.")
    else:
        if stats["invalid_response"] > 0:
            print("\n::warning::DHLottery returned non-JSON responses. Existing feed preserved.")
        elif stats["network_error"] > 0:
            print("\n::warning::DHLottery endpoint unreachable. Existing feed preserved.")
        elif stats["unavailable"] > 0:
            print("\nNo new draw available yet.")
        else:
            print("\nNo changes made.")

if __name__ == "__main__":
    main()
