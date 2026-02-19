import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

TRAVELINE_ENDPOINT = "https://www.traveline.info/TravelInfo/eMBAPI/"

STOP_CODES = {
    "lincoln_road_adj": "oxfadpwj",
    "lincoln_road_opp": "oxfadpwg",
}

def build_siri_request(stop_code: str, requestor_ref: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Siri version="1.3" xmlns="http://www.siri.org.uk/siri">
    <ServiceRequest>
        <RequestorRef>{requestor_ref}</RequestorRef>
        <StopMonitoringRequest version="1.3">
            <Target>
                <MonitoringRef>{stop_code}</MonitoringRef>
            </Target>
            <RequestEndpoint>1</RequestEndpoint>
            <Status>true</Status>
        </StopMonitoringRequest>
    </ServiceRequest>
</Siri>"""

def parse_response(xml_content: str) -> list[dict]:
    departures = []
    ns = {"siri": "http://www.siri.org.uk/siri"}
    
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"Failed to parse XML: {e}")
        return departures
    
    stop_monitoring_deliveries = root.findall(".//siri:StopMonitoringDelivery", ns)
    if not stop_monitoring_deliveries:
        stop_monitoring_deliveries = root.findall(".//StopMonitoringDelivery")
    
    for delivery in stop_monitoring_deliveries:
        monitorings = delivery.findall(".//siri:MonitoredStopVisit", ns)
        if not monitorings:
            monitorings = delivery.findall(".//MonitoredStopVisit")
        
        for visit in monitorings:
            line_ref = _find_text(visit, ".//siri:LineRef", ns) or _find_text(visit, ".//LineRef", ns)
            direction = _find_text(visit, ".//siri:DestinationName", ns) or _find_text(visit, ".//DestinationName", ns)
            aimed_departure = _find_text(visit, ".//siri:AimedDepartureTime", ns) or _find_text(visit, ".//AimedDepartureTime", ns)
            expected_departure = _find_text(visit, ".//siri:ExpectedDepartureTime", ns) or _find_text(visit, ".//ExpectedDepartureTime", ns)
            
            if line_ref:
                departures.append({
                    "line": line_ref,
                    "destination": direction or "Unknown",
                    "aimed": aimed_departure,
                    "expected": expected_departure,
                })
    
    return departures

def _find_text(element: ET.Element, path: str, ns: dict) -> Optional[str]:
    found = element.find(path, ns)
    return found.text if found is not None else None

def format_time(iso_time: Optional[str]) -> str:
    if not iso_time:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except ValueError:
        return iso_time[:5] if iso_time else "N/A"

def get_departures(
    stop_code: str,
    requestor_ref: str,
    username: str,
    password: str
) -> list[dict]:
    xml_request = build_siri_request(stop_code, requestor_ref)
    
    auth = (username, password)
    headers = {"Content-Type": "application/xml"}
    
    response = requests.post(
        TRAVELINE_ENDPOINT,
        data=xml_request.encode("utf-8"),
        auth=auth,
        headers=headers,
        timeout=30
    )
    
    response.raise_for_status()
    return parse_response(response.text)

def print_departures(departures: list[dict], stop_name: str = "Lincoln Road"):
    print(f"\n{'='*50}")
    print(f"Bus Departures - {stop_name}")
    print(f"{'='*50}")
    print(f"{'Line':<8} {'Destination':<25} {'Aimed':<8} {'Expected':<8}")
    print("-" * 50)
    
    if not departures:
        print("No departures found.")
        return
    
    for dep in departures:
        aimed = format_time(dep["aimed"])
        expected = format_time(dep["expected"])
        print(f"{dep['line']:<8} {dep['destination'][:24]:<25} {aimed:<8} {expected:<8}")

def main():
    USERNAME = "YOUR_USERNAME"
    PASSWORD = "YOUR_PASSWORD"
    REQUESTOR_REF = "YOUR_APP_ID"
    
    stop_code = STOP_CODES["lincoln_road_adj"]
    
    print("Fetching bus times for Lincoln Road, New Hinksey...")
    print(f"Stop code: {stop_code}")
    
    try:
        departures = get_departures(
            stop_code=stop_code,
            requestor_ref=REQUESTOR_REF,
            username=USERNAME,
            password=PASSWORD
        )
        print_departures(departures)
    except requests.RequestException as e:
        print(f"Error fetching bus times: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
