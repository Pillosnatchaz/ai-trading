import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import urllib.request
import xml.etree.ElementTree as ET
import datetime as dt
from zoneinfo import ZoneInfo
from core.config import FF_CALENDAR_URL

try:
    req = urllib.request.Request(FF_CALENDAR_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as response:
        xml_data = response.read()
    root = ET.fromstring(xml_data)
    
    now = dt.datetime.now(ZoneInfo("America/New_York"))
    print(f"Current NY Time: {now}")
    
    for event in root.findall('event'):
        impact = event.findtext('impact', '').strip()
        if impact in ('High', 'Medium', 'Low'):
            date_str = event.findtext('date', '').strip()
            time_str = event.findtext('time', '').strip()
            title = event.findtext('title', 'Unknown')
            
            if time_str in ('Tentative', 'All Day'):
                print(f"[{impact}] {title} at {date_str} {time_str}")
                continue
                
            event_dt = dt.datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
            event_dt = event_dt.replace(tzinfo=ZoneInfo("America/New_York"))
            
            mins_diff = (event_dt - now).total_seconds() / 60.0
            print(f"[{impact}] {title} at {event_dt} (in {mins_diff:.1f} mins)")
except Exception as e:
    print(f"Error: {e}")
