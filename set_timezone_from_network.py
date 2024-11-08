import requests
from datetime import datetime, timezone
import pytz

def get_timezone_from_ip():
    try:
        # Request timezone information based on IP location
        response = requests.get("https://ipapi.co/timezone")
        if response.status_code == 200:
            timezone = response.text.strip()
            return timezone
        else:
            print(f"Failed to get timezone: {response.status_code}")
    except Exception as e:
        print(f"Error fetching timezone: {e}")
    return None

def convert_to_local_time(utc_time, timezone_str):
    # Define the local timezone from the detected timezone string
    local_tz = pytz.timezone(timezone_str)
    
    # Convert UTC time to local time with automatic DST adjustment
    return utc_time.astimezone(local_tz)

# Get UTC timestamp
utc_timestamp = datetime.now(timezone.utc)

# Get timezone dynamically from IP
timezone_str = get_timezone_from_ip()
if timezone_str:
    # Convert to detected local timezone
    local_time = convert_to_local_time(utc_timestamp, timezone_str)
    print(f"Local Time in {timezone_str}:", local_time)
else:
    print("Could not retrieve timezone, defaulting to UTC.")
    print("UTC Time:", utc_timestamp)
