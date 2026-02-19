import requests
from bs4 import BeautifulSoup
from typing import Optional
from datetime import datetime

BUSTIMES_URL = "https://bustimes.org/stops/340000990OPP"

WLED_HOST = "192.168.1.180"
WLED_WIDTH = 64
WLED_HEIGHT = 8

NUM_BUSES = 2
MIN_MINUTES = 3

STOP_NAMES = {
    "340000418PR": "Oxford Redbridge Park and Ride (inside)",
    "340000990OPP": "New Hinksey, opposite Lincoln Road",
    "340000990CNR": "Lincoln Road (adj)",
}

def get_departures(stop_code: str = "340000418PR") -> list[dict]:
    url = f"https://bustimes.org/stops/{stop_code}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    
    return parse_html(response.text)

def parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    departures = []
    
    departures_div = soup.find("div", id="departures")
    if not departures_div:
        return departures
    
    table = departures_div.find("table")
    if not table:
        return departures
    
    tbody = table.find("tbody")
    if not tbody:
        return departures
    
    rows = tbody.find_all("tr")
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        
        line_cell = cols[0]
        dest_cell = cols[1]
        sched_cell = cols[2]
        expect_cell = cols[3] if len(cols) > 3 else None
        
        line_link = line_cell.find("a")
        line = line_link.get_text(strip=True) if line_link else ""
        
        if not line:
            continue
        
        destination = ""
        for text in dest_cell.stripped_strings:
            destination = text
            break
        
        scheduled = sched_cell.get_text(strip=True) if sched_cell else ""
        
        expected = ""
        if expect_cell:
            expect_link = expect_cell.find("a")
            expected = expect_link.get_text(strip=True) if expect_link else ""
        
        if scheduled:
            departures.append({
                "line": line,
                "destination": destination,
                "scheduled": scheduled,
                "expected": expected if expected else scheduled,
            })
    
    return departures

def print_departures(departures: list[dict], stop_name: str = "New Hinksey, opposite Lincoln Road"):
    print(f"\n{'='*60}")
    print(f"Bus Departures - {stop_name}")
    print(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")
    print(f"{'Line':<8} {'Destination':<28} {'Scheduled':<12} {'Expected':<10} {'Mins':<5}")
    print("-" * 65)
    
    for dep in departures:
        expected = dep["expected"] if dep["expected"] != dep["scheduled"] else "-"
        mins = minutes_until(dep["expected"] if dep["expected"] else dep["scheduled"])
        mins_str = f"{mins}m" if mins is not None else "-"
        print(f"{dep['line']:<8} {dep['destination'][:27]:<28} {dep['scheduled']:<12} {expected:<10} {mins_str:<5}")

def get_next_bus(departures: list[dict]) -> Optional[dict]:
    if not departures:
        return None
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    for dep in departures:
        bus_time = dep["expected"] if dep["expected"] else dep["scheduled"]
        mins = minutes_until(bus_time)
        if mins is not None and mins > 0:
            return dep
    return departures[0] if departures else None

def minutes_until(time_str: str) -> Optional[int]:
    try:
        bus_time = datetime.strptime(time_str, "%H:%M")
        now = datetime.now()
        bus_dt = now.replace(hour=bus_time.hour, minute=bus_time.minute, second=0, microsecond=0)
        if bus_dt <= now:
            return 0
        diff = (bus_dt - now).total_seconds() / 60
        return int(diff)
    except ValueError:
        return None

def get_next_buses(departures: list[dict], count: int = 4) -> list[dict]:
    if not departures:
        return []
    
    sorted_departures = sorted(
        departures,
        key=lambda d: minutes_until(d["expected"] if d["expected"] else d["scheduled"]) or float("inf")
    )
    
    result = []
    for dep in sorted_departures:
        bus_time = dep["expected"] if dep["expected"] else dep["scheduled"]
        mins = minutes_until(bus_time)
        if mins is not None and mins >= MIN_MINUTES:
            dep["minutes"] = mins
            result.append(dep)
        if len(result) >= count:
            break
    return result

def get_color_for_minutes(minutes: int) -> tuple:
    if minutes < 5:
        return (255, 0, 0)
    elif minutes <= 15:
        return (255, 165, 0)
    else:
        return (0, 255, 0)

def send_to_wled(buses: list[dict]):
    base_url = f"http://{WLED_HOST}"
    
    requests.post(f"{base_url}/json", json={"fx": 106}, timeout=10)
    
    num_segments = 2
    segment_height = WLED_HEIGHT // num_segments
    
    segments = []
    buses_per_seg = (NUM_BUSES + num_segments - 1) // num_segments
    
    for seg_id in range(num_segments):
        start_row = seg_id * segment_height
        start_led = start_row * WLED_WIDTH
        end_led = start_led + (segment_height * WLED_WIDTH)
        
        seg_buses = []
        for i in range(seg_id, NUM_BUSES, num_segments):
            if i < len(buses):
                seg_buses.append(buses[i])
        
        if not seg_buses:
            segments.append({
                "id": seg_id,
                "start": start_led,
                "stop": end_led,
                "n": "",
                "col": [[0, 0, 0, 0]],
                "fx": 0
            })
            continue
        
        text_parts = []
        for bus in seg_buses:
            mins = bus.get("minutes", 0)
            time_str = f"{mins:>3}m"
            text_parts.append(f"{bus['line']:<3}{time_str}")
        
        text = "\n".join(text_parts)
        
        avg_mins = sum(b.get("minutes", 0) for b in seg_buses) // len(seg_buses)
        r, g, b = get_color_for_minutes(avg_mins)
        
        segments.append({
            "id": seg_id,
            "start": start_led,
            "stop": end_led,
            "n": text,
            "col": [[r, g, b, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            "fx": 122,
            "sx": 80,
            "ix": 128
        })
    
    payload = {
        "on": True,
        "bri": 255,
        "seg": segments
    }
    
    try:
        response = requests.post(f"{base_url}/json/state", json=payload, timeout=10)
        response.raise_for_status()
        print(f"WLED updated with {len(buses)} buses")
    except requests.RequestException as e:
        print(f"Error sending to WLED: {e}")

def main():
    stop_code = "340000418PR"
    stop_name = STOP_NAMES.get(stop_code, "Unknown Stop")
    
    print(f"Fetching bus times for {stop_name}...")
    
    try:
        departures = get_departures(stop_code)
        print_departures(departures, stop_name)
        
        next_buses = get_next_buses(departures, NUM_BUSES)
        if next_buses:
            print(f"\nNext 4 buses:")
            for bus in next_buses:
                print(f"  {bus['line']} to {bus['destination']} in {bus.get('minutes', '?')} mins")
            send_to_wled(next_buses)
        else:
            print("No upcoming buses found")
    except requests.RequestException as e:
        print(f"Error fetching bus times: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
