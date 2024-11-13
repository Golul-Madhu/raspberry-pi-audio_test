import os
import time
import threading
import datetime
import sqlite3
import queue
import pyaudio
import wave
import RPi.GPIO as GPIO
import subprocess
import requests
import pytz
from azure.iot.device import IoTHubDeviceClient
from azure.storage.blob import BlobClient

# Constants 1
DATABASE_PATH = "/home/pi/tracking.db"
DATA_FOLDER = "/home/pi/data"
CHUNK = 48000
SAMP_RATE = 48000
FORMAT = pyaudio.paInt16
CHANNELS = 1
RECORD_DURATION = 10  # seconds
TOUCH_PIN = 17
RECORDING_SERVICE = "record_audio.service"
CONNECTION_STRING = "HostName=PRESAGE-IOT-DEV.azure-devices.net;DeviceId=TestDEV01_PRESAGE;SharedAccessKey=qkztrQHEMOiZSnNiOFEa8H3U7M27gZ+P031Y7DhX57Q="
device_client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING, websockets=True)
device_id = CONNECTION_STRING.split("DeviceId=")[1].split(";")[0]

# Global flags for touch control
waiting_to_restart = False
restart_timer = None

# Database operation queue and worker
db_queue = queue.Queue()

# Setup Database
def setup_database():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    connection.commit()
    connection.close()

setup_database()

# Database worker thread to handle all DB operations
def db_worker():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)  # Set timeout to handle potential locks
    cursor = connection.cursor()
    while True:
        operation, data = db_queue.get()
        try:
            if operation == "insert":
                cursor.execute('INSERT INTO files (file_path, status) VALUES (?, ?)', data)
            elif operation == "update":
                cursor.execute('UPDATE files SET status = ? WHERE file_path = ?', data)
            connection.commit()
        except sqlite3.OperationalError as e:
            print(f"Database operation error: {e}. Retrying...")
            time.sleep(0.5)  # Wait briefly and retry on error
            db_queue.put((operation, data))  # Re-queue operation for retry
        finally:
            db_queue.task_done()
    connection.close()

# Start the database worker thread
db_thread = threading.Thread(target=db_worker, daemon=True)
db_thread.start()

# Queueing functions for database operations
def queue_insert_file(file_path):
    db_queue.put(("insert", (file_path, 'to_upload')))

def queue_update_file_status(file_path, status):
    db_queue.put(("update", (status, file_path)))

# Record Audio
def save_audio_buffer(buffer, start_time, end_time):
    audio = pyaudio.PyAudio()
    date_folder = start_time.strftime('%Y-%m-%d')
    os.makedirs(os.path.join(DATA_FOLDER, date_folder), exist_ok=True)
    file_name = f"{device_id}_from_{start_time.strftime('%Y-%m-%d_%H-%M-%S')}_to_{end_time.strftime('%H-%M-%S')}.wav"
    file_path = os.path.join(DATA_FOLDER, date_folder, file_name)

    with wave.open(file_path, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(SAMP_RATE)
        wf.writeframes(b''.join(buffer))

    print(f"Saved audio file: {file_path}")
    audio.terminate()

    # Queue insert operation
    queue_insert_file(file_path)

def record_audio_continuously():
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, rate=SAMP_RATE, channels=CHANNELS, input=True, frames_per_buffer=CHUNK)
    buffer1, buffer2 = [], []
    active_buffer = buffer1

    print("Continuous recording started.")
    try:
        while True:
            start_time = datetime.datetime.now()
            active_buffer.clear()
            for _ in range(0, int(SAMP_RATE / CHUNK * RECORD_DURATION)):
                data = stream.read(CHUNK, exception_on_overflow=False)
                active_buffer.append(data)
            end_time = datetime.datetime.now()
            threading.Thread(target=save_audio_buffer, args=(active_buffer, start_time, end_time), daemon=True).start()
            active_buffer = buffer2 if active_buffer is buffer1 else buffer1
    except KeyboardInterrupt:
        print("Recording stopped by user.")
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

# Delete Old Uploaded Files
def delete_old_uploaded_files():
    while True:
        current_time = datetime.datetime.now()
        connection = sqlite3.connect(DATABASE_PATH, timeout=10)
        cursor = connection.cursor()
        cursor.execute('SELECT file_path, timestamp FROM files WHERE status = "uploaded"')
        uploaded_files = cursor.fetchall()
        connection.close()

        for file_path, timestamp in uploaded_files:
            file_time = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            if (current_time - file_time).days >= 1:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Deleted file: {file_path}")

        time.sleep(3600)

# Touch Control
GPIO.setmode(GPIO.BCM)
GPIO.setup(TOUCH_PIN, GPIO.IN)

def start_recording_service():
    global waiting_to_restart, restart_timer
    if restart_timer:
        restart_timer.cancel()
        restart_timer = None
    waiting_to_restart = False
    subprocess.run(["sudo", "systemctl", "start", RECORDING_SERVICE])
    print("Recording service started immediately due to 3-second touch.")

def stop_recording_service():
    global waiting_to_restart, restart_timer
    subprocess.run(["sudo", "systemctl", "stop", RECORDING_SERVICE])
    print("Recording service stopped. Will restart after 1 hour if not manually started.")
    waiting_to_restart = True
    restart_timer = threading.Timer(3600, start_recording_service)
    restart_timer.start()

def monitor_touch():
    try:
        while True:
            if GPIO.input(TOUCH_PIN) == GPIO.HIGH:
                time.sleep(3)
                if GPIO.input(TOUCH_PIN) == GPIO.HIGH:
                    if waiting_to_restart:
                        start_recording_service()
                    elif subprocess.run(["systemctl", "is-active", "--quiet", RECORDING_SERVICE]).returncode == 0:
                        stop_recording_service()
                    else:
                        start_recording_service()
    except KeyboardInterrupt:
        print("Touch control exited.")
    finally:
        GPIO.cleanup()

# Upload to Cloud
def upload_file(file_path):
    try:
        blob_name = f"{os.path.relpath(file_path, DATA_FOLDER).replace(os.sep, '/')}"
        blob_info = device_client.get_storage_info_for_blob(blob_name)
        sas_url = f"https://{blob_info['hostName']}/{blob_info['containerName']}/{blob_info['blobName']}{blob_info['sasToken']}"
        with BlobClient.from_blob_url(sas_url) as blob_client, open(file_path, "rb") as file:
            blob_client.upload_blob(file, overwrite=True)
        device_client.notify_blob_upload_status(blob_info["correlationId"], True, 200, "Upload successful.")
        print(f"Upload successful for {file_path}")
        queue_update_file_status(file_path, 'uploaded')
    except Exception as e:
        print(f"Failed to upload {file_path}: {e}")

def upload_worker():
    while True:
        connection = sqlite3.connect(DATABASE_PATH, timeout=10)
        cursor = connection.cursor()
        cursor.execute('SELECT file_path FROM files WHERE status = "to_upload" ORDER BY timestamp ASC')
        files_to_upload = cursor.fetchall()
        connection.close()

        for (file_path,) in files_to_upload:
            upload_file(file_path)

        time.sleep(10)

# Timezone Adjustment

def get_timezone_from_ip():
    try:
        response = requests.get("https://ipinfo.io/json", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("timezone")
        else:
            print(f"Failed to get timezone. Status code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"Error fetching timezone: {e}")
    return None

def set_local_time():
    # Get UTC timestamp
    utc_timestamp = datetime.datetime.now(datetime.timezone.utc)
    timezone_str = get_timezone_from_ip()
    if timezone_str:
        # Define the local timezone and convert the time
        local_tz = pytz.timezone(timezone_str)
        local_time = utc_timestamp.astimezone(local_tz)
        print(f"Local Time in {timezone_str}: {local_time}")
    else:
        print("Could not retrieve timezone. UTC time:", utc_timestamp)

# Main Program Threads
if __name__ == "__main__":
    threading.Thread(target=record_audio_continuously, daemon=True).start()
    threading.Thread(target=delete_old_uploaded_files, daemon=True).start()
    threading.Thread(target=monitor_touch, daemon=True).start()
    threading.Thread(target=upload_worker, daemon=True).start()
    set_local_time()
    while True:
        time.sleep(1)
