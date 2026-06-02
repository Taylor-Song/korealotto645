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
SMOK95_LATEST_URL = "https://smok95.github.io/lotto/results/latest.json"
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

def get_upstream_latest():
    """Determines the actual latest draw number available upstream."""
    print("Determining upstream latest draw number...")
    
    # Priority 1: smok95 latest.json
    try:
        response = requests.get(SMOK95_LATEST_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            latest = data.get("draw_no")
            if isinstance(latest, int):
                print(f"Upstream latest (smok95 latest.json): {latest}")
                return latest
    except Exception as e:
        print(f"Smok95 latest.json fetch failed: {e}")

    # Priority 2: smok95 all.json
    try:
        response = requests.get(SMOK95_ALL_URL, timeout=15)
        if response.status_code == 200:
            all_data = response.json()
            if all_data:
                latest = max(item.get("draw_no", 0) for item in all_data)
                if latest > 0:
                    print(f"Upstream latest (smok95 all.json): {latest}")
                    return latest
    except Exception as e:
        print(f"Smok95 all.json fetch failed: {e}")

    return None

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
    except Exception:
        return FetchResult.NETWORK_ERROR, None

def normalize_smok95(data):
    """Normalizes smok95 JSON format to our canonical format."""
    try:
        divisions = data.get("divisions", [])
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
    except Exception:
        return None

def fetch_fallback_smok95(draw_no):
    """Fetches a specific draw from smok95 fallback source."""
    try:
        url = SMOK95_PER_DRAW_URL.format(draw_no)
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            norm = normalize_smok95(response.json())
            if norm:
                return FetchResult.SUCCESS, norm
        return FetchResult.INVALID_RESPONSE, None
    except Exception:
        return FetchResult.NETWORK_ERROR, None

def main():
    if not os.path.exists(DATA_FILE):
        feed_data = {"schemaVersion": 1, "baseDrawNo": BASE_DRAW_NO, "updatedAt": "", "latestDrawNo": BASE_DRAW_NO, "draws": []}
    else:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            feed_data = json.load(f)

    current_header_latest = feed_data.get("latestDrawNo", BASE_DRAW_NO)
    existing_nos = {d["drawNo"] for d in feed_data["draws"]}
    current_actual_latest = max(existing_nos) if existing_nos else BASE_DRAW_NO
    
    print(f"Current feed latest (header): {current_header_latest}")
    print(f"Current feed latest (actual): {current_actual_latest}")

    upstream_latest = get_upstream_latest()
    if upstream_latest is None:
        print("::warning::Could not determine upstream latest draw. Existing feed preserved.")
        return

    # We want to sync up to upstream_latest, even if current_actual_latest is behind
    missing_range = []
    goal = upstream_latest
    for d_no in range(BASE_DRAW_NO + 1, goal + 1):
        if d_no not in existing_nos:
            missing_range.append(d_no)

    if not missing_range:
        # Check if header needs fix
        if current_header_latest != current_actual_latest:
            print(f"No new draws missing, but fixing header latestDrawNo to {current_actual_latest}")
            feed_data["latestDrawNo"] = current_actual_latest
            feed_data["updatedAt"] = datetime.datetime.utcnow().isoformat() + "Z"
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(feed_data, f, ensure_ascii=False, indent=2)
            print("Done.")
        else:
            print(f"No new draw available and header is consistent. (Upstream: {upstream_latest})")
        return

    print(f"Missing range: {missing_range[0]}..{missing_range[-1]} ({len(missing_range)} draws)")

    # Pre-load all.json
    cached_fallback_data = {}
    try:
        print("Fetching all.json from fallback to speed up sync...")
        response = requests.get(SMOK95_ALL_URL, timeout=15)
        if response.status_code == 200:
            for item in response.json():
                d_no = item.get("draw_no")
                if d_no in missing_range:
                    norm = normalize_smok95(item)
                    if norm:
                        cached_fallback_data[d_no] = norm
        print(f"Pre-loaded {len(cached_fallback_data)} draws from all.json")
    except Exception:
        print("Failed to pre-load all.json, will fetch per-draw.")

    change_count = 0
    for d_no in missing_range:
        # Step 1: Try DHLottery
        res, info = fetch_from_dhlottery(d_no)
        
        # Step 2: Try Cached Fallback
        if res != FetchResult.SUCCESS and d_no in cached_fallback_data:
            info = cached_fallback_data[d_no]
            res = FetchResult.SUCCESS
            print(f"Draw {d_no}: Recovered from cached all.json")
        
        # Step 3: Try Per-Draw Fallback
        if res != FetchResult.SUCCESS:
            res, info = fetch_fallback_smok95(d_no)
            if res == FetchResult.SUCCESS:
                print(f"Draw {d_no}: Recovered from smok95 per-draw JSON")

        if res == FetchResult.SUCCESS:
            feed_data["draws"].append(info)
            change_count += 1
        else:
            print(f"::warning::Failed to fetch draw {d_no} from all sources.")

    if change_count > 0 or current_header_latest != current_actual_latest:
        feed_data["draws"].sort(key=lambda x: x["drawNo"])
        actual_max = max(d["drawNo"] for d in feed_data["draws"])
        feed_data["latestDrawNo"] = actual_max
        feed_data["updatedAt"] = datetime.datetime.utcnow().isoformat() + "Z"
        
        temp_file = DATA_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(feed_data, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, DATA_FILE)
        print(f"Summary: Added/Updated {change_count} draws. Final latestDrawNo: {feed_data['latestDrawNo']}")
    else:
        print("No changes made to the feed.")

if __name__ == "__main__":
    main()
