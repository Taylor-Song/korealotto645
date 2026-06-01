import os
import json
import requests
import datetime
import time

DATA_FILE = "data/draws_delta.json"
BASE_DRAW_NO = 1204
API_URL = "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={}"

def fetch_draw_data(draw_no):
    """Fetches draw data from DHLottery API."""
    try:
        response = requests.get(API_URL.format(draw_no), timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("returnValue") == "success":
            return {
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
        else:
            print(f"Draw {draw_no} not available yet (returnValue: {data.get('returnValue')})")
            return None
    except Exception as e:
        print(f"Error fetching draw {draw_no}: {e}")
        return None

def main():
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
    
    # In case latestDrawNo was inconsistent
    start_draw = max(start_draw, current_latest + 1)
    
    print(f"Starting fetch from draw {start_draw}...")
    
    new_draws_count = 0
    consecutive_failures = 0
    max_consecutive_failures = 3 # Stop after 3 fails to avoid endless loops on outages or gaps
    
    target_draw = start_draw
    while consecutive_failures < max_consecutive_failures:
        draw_info = fetch_draw_data(target_draw)
        
        if draw_info:
            feed_data["draws"].append(draw_info)
            feed_data["latestDrawNo"] = draw_info["drawNo"]
            new_draws_count += 1
            consecutive_failures = 0 # Reset failures on success
            print(f"Added draw {target_draw}: {draw_info['drawDate']}")
        else:
            consecutive_failures += 1
            # If dhlottery is reachable but returns "fail", it likely means the draw doesn't exist yet.
        
        target_draw += 1
        time.sleep(1) # Be gentle to the server

    if new_draws_count > 0:
        # Sort draws by number just in case
        feed_data["draws"].sort(key=lambda x: x["drawNo"])
        feed_data["updatedAt"] = datetime.datetime.utcnow().isoformat() + "Z"
        
        # Save atomically
        temp_file = DATA_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(feed_data, f, ensure_ascii=False, indent=2)
        
        os.replace(temp_file, DATA_FILE)
        print(f"Successfully updated {DATA_FILE} with {new_draws_count} new draws.")
    else:
        print("No new draws found.")

if __name__ == "__main__":
    main()
