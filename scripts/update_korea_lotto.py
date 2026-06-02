import os
import json
import requests
import datetime
import time
from enum import Enum

DATA_FILE = "data/draws_delta.json"
BASE_DRAW_NO = 1204

# Sources
DHLOTTERY_URL = "https://www.dhlottery.co.kr/common.do"
SMOK95_ALL_URL = "https://smok95.github.io/lotto/results/all.json"
SMOK95_PER_DRAW_URL = "https://smok95.github.io/lotto/results/{}.json"

class FetchResult(Enum):
    SUCCESS = 1
    UNAVAILABLE = 2
    INVALID_RESPONSE = 3
    NETWORK_ERROR = 4

def validate_draw(draw):
    """Validates if a draw object meets our schema requirements."""
    try:
        if not isinstance(draw.get("drawNo"), int) or draw["drawNo"] <= BASE_DRAW_NO:
            return False
        if not isinstance(draw.get("drawDate"), str) or len(draw["drawDate"]) != 10:
            return False
        if not isinstance(draw.get("numbers"), list) or len(draw["numbers"]) != 6:
            return False
        if any(not isinstance(n, int) or not (1 <= n <= 45) for n in draw["numbers"]):
            return False
        if len(set(draw["numbers"])) != 6:
            return False
        if not isinstance(draw.get("bonusNumber"), int) or not (1 <= draw["bonusNumber"] <= 45):
            return False
        if draw["bonusNumber"] in draw["numbers"]:
            return False
        if draw.get("firstWinnerCount", -1) < 0:
            return False
        if draw.get("firstPrizeAmount", -1) < 0:
            return False
        if draw.get("totalSellAmount", -1) < 0:
            return False
        return True
    except Exception:
        return False

def fetch_from_dhlottery(draw_no):
    """Fetches draw data from official dhlottery endpoint."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://www.dhlottery.co.kr/gameResult.do?method=byWin",
        "X-Requested-With": "XMLHttpRequest"
    }
    params = {"method": "getLottoNumber", "drwNo": draw_no}
    try:
        response = requests.get(DHLOTTERY_URL, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            return FetchResult.INVALID_RESPONSE, None
        
        data = response.json()
        if data.get("returnValue") == "success":
            draw_info = {
                "drawNo": int(data["drwNo"]),
                "drawDate": data["drwNoDate"],
                "numbers": [
                    int(data["drwtNo1"]), int(data["drwtNo2"]), int(data["drwtNo3"]),
                    int(data["drwtNo4"]), int(data["drwtNo5"]), int(data["drwtNo6"])
                ],
                "bonusNumber": int(data["bnusNo"]),
                "firstWinnerCount": int(data["firstPrzwnerCo"]),
                "firstPrizeAmount": int(data["firstWinPrizamnt"]),
                "totalSellAmount": int(data["totSellamnt"])
            }
            if validate_draw(draw_info):
                return FetchResult.SUCCESS, draw_info
            return FetchResult.INVALID_RESPONSE, None
        return FetchResult.UNAVAILABLE, None
    except Exception as e:
        print(f"DHLottery fetch error for {draw_no}: {e}")
        return FetchResult.NETWORK_ERROR, None

def normalize_smok95(data):
    """Normalizes smok95 JSON format to our canonical format."""
    try:
        divisions = data.get("divisions", [])
        # In smok95 format, divisions[0] is typically the 1st prize.
        # If 1st prize had no winners, it might be an empty dict or missing.
        p1 = divisions[0] if len(divisions) > 0 and isinstance(divisions[0], dict) else {}
        
        draw_info = {
            "drawNo": int(data["draw_no"]),
            "drawDate": data["date"][:10],
            "numbers": data["numbers"],
            "bonusNumber": data["bonus_no"],
            "firstWinnerCount": p1.get("winners", 0),
            "firstPrizeAmount": p1.get("prize", 0),
            "totalSellAmount": data.get("total_sales_amount", 0)
        }
        if validate_draw(draw_info):
            return draw_info
        return None
    except Exception as e:
        print(f"Smok95 normalization error: {e}")
        return None

def fetch_fallback_smok95(missing_draws):
    """Fetches missing draws from smok95 fallback source."""
    results = {}
    print(f"Trying smok95 fallback source for missing draws: {missing_draws}")
    
    # Strategy: try all.json first as it's efficient for multiple draws
    try:
        response = requests.get(SMOK95_ALL_URL, timeout=15)
        if response.status_code == 200:
            all_data = response.json()
            for item in all_data:
                d_no = item.get("draw_no")
                if d_no in missing_draws:
                    norm = normalize_smok95(item)
                    if norm:
                        results[d_no] = norm
            if results:
                print(f"Recovered {len(results)} draws from smok95 all.json")
                return results
    except Exception as e:
        print(f"Smok95 all.json fetch failed: {e}")

    # If all.json didn't have all we need, try per-draw as last resort
    remaining = [d for d in missing_draws if d not in results]
    for d_no in remaining:
        try:
            url = SMOK95_PER_DRAW_URL.format(d_no)
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                norm = normalize_smok95(response.json())
                if norm:
                    results[d_no] = norm
                    print(f"Recovered draw {d_no} from smok95 per-draw JSON")
            time.sleep(0.5)
        except Exception:
            pass
            
    return results

def main():
    if not os.path.exists(DATA_FILE):
        feed_data = {"schemaVersion": 1, "baseDrawNo": BASE_DRAW_NO, "updatedAt": "", "latestDrawNo": BASE_DRAW_NO, "draws": []}
    else:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            feed_data = json.load(f)

    # Determine what's missing
    existing_nos = {d["drawNo"] for d in feed_data["draws"]}
    current_max = max(existing_nos) if existing_nos else BASE_DRAW_NO
    
    # We estimate the current draw number to probe dhlottery
    # 1204 was around Feb 2026. 
    # Today is June 2026. Roughly 15 weeks passed (~1219).
    # We probe up to current_max + 10 or until failures.
    
    found_any = False
    new_draws = {}
    
    print(f"Current feed latest: {current_max}")
    print("Trying official dhlottery source...")
    
    target_draw = current_max + 1
    fail_count = 0
    while fail_count < 2:
        res, info = fetch_from_dhlottery(target_draw)
        if res == FetchResult.SUCCESS:
            new_draws[target_draw] = info
            fail_count = 0
            print(f"Added draw {target_draw} from dhlottery")
        elif res == FetchResult.UNAVAILABLE:
            # Likely reached the future
            break
        else:
            # Network or Invalid response
            print(f"::warning::dhlottery failed for {target_draw} (result: {res.name})")
            fail_count += 1
        target_draw += 1
        time.sleep(1)

    # If we missed any draws (e.g. gaps between current_max and where dhlottery failed)
    # OR if dhlottery didn't return anything at all but we suspect newer data exists.
    # We'll use fallback to fill gaps and extend.
    
    # Probe a bit further with fallback just in case
    missing_candidates = list(range(current_max + 1, current_max + 30))
    # Filter out what we already got from dhlottery
    missing_candidates = [d for d in missing_candidates if d not in new_draws and d not in existing_nos]
    
    fallback_results = fetch_fallback_smok95(missing_candidates)
    new_draws.update(fallback_results)

    if new_draws:
        # Merge
        for d_no in sorted(new_draws.keys()):
            if d_no not in existing_nos:
                feed_data["draws"].append(new_draws[d_no])
        
        feed_data["draws"].sort(key=lambda x: x["drawNo"])
        feed_data["latestDrawNo"] = max(d["drawNo"] for d in feed_data["draws"])
        feed_data["updatedAt"] = datetime.datetime.utcnow().isoformat() + "Z"
        
        # Atomic write
        temp_file = DATA_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(feed_data, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, DATA_FILE)
        print(f"Successfully updated feed to draw {feed_data['latestDrawNo']} (added {len(new_draws)} draws)")
    else:
        print("No new valid draws found from any source.")

if __name__ == "__main__":
    main()
