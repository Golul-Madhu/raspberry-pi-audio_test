import os
import time
import subprocess
import pyaudio
import wave
import datetime
import sqlite3
import requests
import pytz
import threading
from azure.iot.device import IoTHubDeviceClient
from azure.storage.blob import BlobClient

# Configuration for Azure IoT
CONNECTION_STRING = "HostName=PRESAGE.azure-devices.net;DeviceId=ESP32C6_INMP441;SharedAccessKey=LzQLb2rlspLU4hzMep7zw/bJObpsS2K7LAIoTH/cxMA="

# Audio Recording Parameters
CHUNK = 48000
SAMP_RATE = 48000
FORMAT = pyaudio.paInt16
CHANNELS = 1
RECORD_DURATION = 10  # Duration of each recording segment in seconds
DATA_FOLDER = "/home/pi/data"
DEVICE_ID = CONNECTION_STRING.split("DeviceId=")[1].split(";")[0]"

# Network Configuration
PING_IP = "8.8.8.8"  # IP address to check for internet connectivity
WIFI_METRIC = 600
PPP_METRIC = 700
wifi_route = None  # Global variable for the WiFi route

# Initialize Azure IoT client
device_client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING, websockets=True)

def get_timezone_from_ip():
    """Fetch timezone based on device's IP address."""
    try:
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
    """Convert UTC timestamp to local time based on detected timezone."""
    local_tz = pytz.timezone(timezone_str)
    return utc_time.astimezone(local_tz)

def ensure_wvdial_running():
    """Ensure that wvdial is running for the 4G connection, start if not."""
    result = subprocess.run(["pgrep", "wvdial"], stdout=subprocess.DEVNULL)
    if result.returncode != 0:
        subprocess.Popen(["sudo", "wvdial"])

def get_wifi_gateway():
    """Determine the default gateway for WiFi."""
    try:
        result = subprocess.check_output(["ip", "route", "show", "default", "0.0.0.0/0"], encoding="utf-8")
        if "wlan0" in result:
            return result.split()[2]
    except subprocess.CalledProcessError:
        print("Could not determine WiFi gateway.")
    return None

def monitor_network():
    """Continuously monitor the network and set the default route based on WiFi or 4G connectivity."""
    global wifi_route
    while True:
        ensure_wvdial_running()
        wifi_route = get_wifi_gateway()

        if wifi_route:
            subprocess.run(["ip", "route", "add", "default", "via", wifi_route, "dev", "wlan0", "metric", str(WIFI_METRIC)], check=False)
            if subprocess.run(["ping", "-c", "1", "-I", "wlan0", PING_IP], stdout=subprocess.DEVNULL).returncode == 0:
                print("Using WiFi as default route.")
                subprocess.run(["ip", "route", "del", "default", "dev", "ppp0", "metric", str(PPP_METRIC)], check=False)
            else:
                print("WiFi unavailable. Switching to 4G as default route.")
                subprocess.run(["ip", "route", "replace", "default", "dev", "ppp0", "metric", str(PPP_METRIC)], check=False)
                subprocess.run(["ip", "route", "del", "default", "dev", "wlan0", "metric", str(WIFI_METRIC)], check=False)
        else:
            print("WiFi route not found, defaulting to 4G.")
        
        time.sleep(10)

def save_audio(buffer, start_time, timezone_str):
    """Save the recorded audio buffer to a WAV file with local time in filename."""
    local_start_time = convert_to_local_time(start_time, timezone_str)
    date_folder = os.path.join(DATA_FOLDER, DEVICE_ID, local_start_time.strftime('%Y-%m-%d'))
    os.makedirs(date_folder, exist_ok=True)

    end_time = datetime.datetime.now(datetime.timezone.utc)
    local_end_time = convert_to_local_time(end_time, timezone_str)
    file_name = f"{DEVICE_ID}_{local_start_time.strftime('%Y-%m-%d_%H_%M_%S')}_to_{local_end_time.strftime('%H_%M_%S')}.wav"
    file_path = os.path.join(date_folder, file_name)

    with wave.open(file_path, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pyaudio.PyAudio().get_sample_size(FORMAT))
        wf.setframerate(SAMP_RATE)
        wf.writeframes(b''.join(buffer))

    # Log file to database as "to_upload"
    with sqlite3.connect('tracking.db') as conn:
        conn.execute('INSERT OR REPLACE INTO files (file_path, status) VALUES (?, ?)', (file_path, "to_upload"))
        conn.commit()
    
    print(f"Saved audio file: {file_path}")

def record_audio():
    """Continuously record audio in 10-second segments and save locally."""
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, rate=SAMP_RATE, channels=CHANNELS, input=True, frames_per_buffer=CHUNK)

    buffer1, buffer2 = [], []
    active_buffer = buffer1
    timezone_str = get_timezone_from_ip() or "UTC"

    print("Continuous recording started.")
    while True:
        start_time = datetime.datetime.now(datetime.timezone.utc)
        active_buffer.clear()
        for _ in range(0, int(SAMP_RATE / CHUNK * RECORD_DURATION)):
            active_buffer.append(stream.read(CHUNK, exception_on_overflow=False))

        # Save the recorded segment
        save_audio(list(active_buffer), start_time, timezone_str)

def upload_to_cloud():
    """Upload files marked as 'to_upload' to Azure IoT and update status in database."""
    while True:
        with sqlite3.connect('tracking.db') as conn:
            cursor = conn.execute('SELECT file_path FROM files WHERE status = "to_upload"')
            files_to_upload = cursor.fetchall()
        
        for (file_path,) in files_to_upload:
            try:
                blob_name = os.path.basename(file_path)
                blob_info = device_client.get_storage_info_for_blob(blob_name)
                sas_url = f"https://{blob_info['hostName']}/{blob_info['containerName']}/{blob_info['blobName']}{blob_info['sasToken']}"
                
                with BlobClient.from_blob_url(sas_url) as blob_client, open(file_path, "rb") as file:
                    blob_client.upload_blob(file, overwrite=True)
                device_client.notify_blob_upload_status(blob_info["correlationId"], True, 200, "Upload successful.")
                
                with sqlite3.connect('tracking.db') as conn:
                    conn.execute('UPDATE files SET status = "uploaded" WHERE file_path = ?', (file_path,))
                    conn.commit()
                print(f"Uploaded file to cloud: {file_path}")

            except Exception as e:
                print(f"Failed to upload {file_path}: {e}")
        
        time.sleep(10)

def delete_uploaded_files():
    """Delete files older than 24 hours if they are marked as 'uploaded'."""
    while True:
        cutoff_time = time.time() - 24 * 3600  # 24 hours ago
        with sqlite3.connect('tracking.db') as conn:
            cursor = conn.execute('SELECT file_path FROM files WHERE status = "uploaded"')
            for (file_path,) in cursor.fetchall():
                if os.path.getmtime(file_path) < cutoff_time:
                    try:
                        os.remove(file_path)
                        conn.execute('DELETE FROM files WHERE file_path = ?', (file_path,))
                        conn.commit()
                        print(f"Deleted old file: {file_path}")
                    except FileNotFoundError:
                        print(f"File not found for deletion: {file_path}")
        time.sleep(3600)

def setup_database():
    """Create the tracking database if it doesn't exist."""
    with sqlite3.connect('tracking.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS files (
                        file_path TEXT PRIMARY KEY,
                        status TEXT)''')
        conn.commit()

def check_for_updates():
    """Check for updates on GitHub, pull changes if available, and restart the script."""
    REPO_PATH = "/home/pi/raspberry-pi-audio_test"
    while True:
        os.chdir(REPO_PATH)
        subprocess.run(["git", "fetch", "origin"])
        local_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip()
        remote_commit = subprocess.check_output(["git", "rev-parse", "origin/main"]).strip()
        
        if local_commit != remote_commit:
            print("New update detected. Pulling changes and restarting...")
            subprocess.run(["git", "reset", "--hard", "origin/main"])
            os.execv(__file__, ["python3"] + sys.argv)
        
        time.sleep(3600)  # Check for updates every hour

if __name__ == "__main__":
    setup_database()
    
    threading.Thread(target=record_audio, daemon=True).start()
    threading.Thread(target=upload_to_cloud, daemon=True).start()
    threading.Thread(target=delete_uploaded_files, daemon=True).start()
    threading.Thread(target=monitor_network, daemon=True).start()
    threading.Thread(target=check_for_updates, daemon=True).start()
