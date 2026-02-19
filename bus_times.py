"""
Bus departure display for WLED LED matrix.
Fetches real-time bus times from bustimes.org and displays on LED matrix.
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional

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
    """Fetch departures from bustimes.org for given stop code."""
    url = f"https://bustimes.org/stops/{stop_code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return parse_html(response.text)


def parse_html(html: str) -> list[dict]:
    """Parse HTML response and extract departure information."""
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

    for row in tbody.find_all("tr"):
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

        destination = next(dest_cell.stripped_strings, "")

        scheduled = sched_cell.get_text(strip=True) if sched_cell else ""
        if not scheduled:
            continue

        expected = ""
        if expect_cell:
            expect_link = expect_cell.find("a")
            expected = expect_link.get_text(strip=True) if expect_link else ""

        departures.append({
            "line": line,
            "destination": destination,
            "scheduled": scheduled,
            "expected": expected or scheduled,
        })

    return departures


def minutes_until(time_str: str) -> Optional[int]:
    """Calculate minutes until given time string (HH:MM format)."""
    try:
        bus_time = datetime.strptime(time_str, "%H:%M")
        now = datetime.now()
        bus_dt = now.replace(
            hour=bus_time.hour,
            minute=bus_time.minute,
            second=0,
            microsecond=0,
        )
        if bus_dt <= now:
            return 0
        return int((bus_dt - now).total_seconds() / 60)
    except ValueError:
        return None


def get_color_for_minutes(minutes: int) -> tuple:
    """Return RGB color tuple based on minutes until arrival."""
    if minutes < 5:
        return (255, 0, 0)
    if minutes <= 15:
        return (255, 165, 0)
    return (0, 255, 0)


def get_next_buses(departures: list[dict], count: int = 4) -> list[dict]:
    """Get next N buses sorted by arrival time, filtered by MIN_MINUTES."""
    if not departures:
        return []

    def sort_key(dep: dict) -> float:
        time_str = dep.get("expected") or dep.get("scheduled", "")
        return minutes_until(time_str) or float("inf")

    sorted_departures = sorted(departures, key=sort_key)

    result = []
    for dep in sorted_departures:
        time_str = dep.get("expected") or dep.get("scheduled", "")
        mins = minutes_until(time_str)
        if mins is not None and mins >= MIN_MINUTES:
            dep["minutes"] = mins
            result.append(dep)
        if len(result) >= count:
            break
    return result


def get_next_bus(departures: list[dict]) -> Optional[dict]:
    """Get the next upcoming bus."""
    if not departures:
        return None

    for dep in departures:
        time_str = dep.get("expected") or dep.get("scheduled", "")
        mins = minutes_until(time_str)
        if mins is not None and mins > 0:
            return dep
    return departures[0] if departures else None


def print_departures(departures: list[dict], stop_name: str) -> None:
    """Print departures to console."""
    print(f"\n{'=' * 60}")
    print(f"Bus Departures - {stop_name}")
    print(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'=' * 60}")
    print(f"{'Line':<8} {'Destination':<28} {'Scheduled':<12} "
          f"{'Expected':<10} {'Mins':<5}")
    print("-" * 65)

    for dep in departures:
        expected = (dep["expected"]
                    if dep["expected"] != dep["scheduled"]
                    else "-")
        time_str = dep.get("expected") or dep.get("scheduled", "")
        mins = minutes_until(time_str)
        mins_str = f"{mins}m" if mins is not None else "-"
        print(f"{dep['line']:<8} {dep['destination'][:27]:<28} "
              f"{dep['scheduled']:<12} {expected:<10} {mins_str:<5}")


def send_to_wled(buses: list[dict]) -> None:
    """Send bus times to WLED LED matrix."""
    base_url = f"http://{WLED_HOST}"

    requests.post(f"{base_url}/json", json={"fx": 106}, timeout=10)

    num_segments = 2
    segment_height = WLED_HEIGHT // num_segments
    segments = []

    for seg_id in range(num_segments):
        start_row = seg_id * segment_height
        start_led = start_row * WLED_WIDTH
        end_led = start_led + (segment_height * WLED_WIDTH)

        seg_buses = [buses[i] for i in range(seg_id, NUM_BUSES, num_segments)
                     if i < len(buses)]

        if not seg_buses:
            segments.append({
                "id": seg_id,
                "start": start_led,
                "stop": end_led,
                "n": "",
                "col": [[0, 0, 0, 0]],
                "fx": 0,
            })
            continue

        text = "\n".join(
            f"{bus['line']:<3}{bus.get('minutes', 0):>3}m"
            for bus in seg_buses
        )

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
            "ix": 128,
        })

    payload = {"on": True, "bri": 255, "seg": segments}

    try:
        response = requests.post(f"{base_url}/json/state",
                                 json=payload, timeout=10)
        response.raise_for_status()
        print(f"WLED updated with {len(buses)} buses")
    except requests.RequestException as e:
        print(f"Error sending to WLED: {e}")


def main():
    """Main entry point."""
    stop_code = "340000418PR"
    stop_name = STOP_NAMES.get(stop_code, "Unknown Stop")

    print(f"Fetching bus times for {stop_name}...")

    try:
        departures = get_departures(stop_code)
        print_departures(departures, stop_name)

        next_buses = get_next_buses(departures, NUM_BUSES)
        if next_buses:
            print(f"\nNext {len(next_buses)} buses:")
            for bus in next_buses:
                print(f"  {bus['line']} to {bus['destination']} "
                      f"in {bus.get('minutes', '?')} mins")
            send_to_wled(next_buses)
        else:
            print("No upcoming buses found")
    except requests.RequestException as e:
        print(f"Error fetching bus times: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
