import os
import time
import threading
import datetime
import sqlite3
import pyaudio
import wave
import RPi.GPIO as GPIO
import subprocess
import requests
import pytz
from azure.iot.device import IoTHubDeviceClient
from azure.storage.blob import BlobClient

# Constants TESTING 1
DATABASE_PATH = "/home/pi/tracking.db"
DATA_FOLDER = "/home/pi/data"
CHUNK = 48000
SAMP_RATE = 48000
FORMAT = pyaudio.paInt16
CHANNELS = 1
RECORD_DURATION = 10  # seconds
TOUCH_PIN = 17
RECORDING_SERVICE = "record_audio.service"
CONNECTION_STRING = "HostName=PRESAGE.azure-devices.net;DeviceId=ESP32C6_INMP441;SharedAccessKey=LzQLb2rlspLU4hzMep7zw/bJObpsS2K7LAIoTH/cxMA="
device_client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING, websockets=True)
device_id = CONNECTION_STRING.split("DeviceId=")[1].split(";")[0]

# Global flag and timer variable for touch control
waiting_to_restart = False
restart_timer = None

# Setup Database
def setup_database():
    connection = sqlite3.connect(DATABASE_PATH)
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

    # Insert file path into database
    connection = sqlite3.connect(DATABASE_PATH)
    cursor = connection.cursor()
    cursor.execute('INSERT INTO files (file_path, status) VALUES (?, ?)', (file_path, 'to_upload'))
    connection.commit()
    connection.close()

def record_audio_continuously():
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, rate=SAMP_RATE, channels=CHANNELS, input=True, frames_per_buffer=CHUNK)
    buffer1, buffer2 = [], []
    active_buffer = buffer1

    print("Continuous recording started. Press Ctrl+C to stop.")
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
        connection = sqlite3.connect(DATABASE_PATH)
        cursor = connection.cursor()
        cursor.execute('SELECT file_path, timestamp FROM files WHERE status = "uploaded"')
        uploaded_files = cursor.fetchall()

        for file_path, timestamp in uploaded_files:
            file_time = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            if (current_time - file_time).days >= 1:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Deleted file: {file_path}")

        connection.close()
        time.sleep(3600)  # Check every hour

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
    # Set up a timer to automatically restart after 1 hour
    restart_timer = threading.Timer(3600, start_recording_service)
    restart_timer.start()

def monitor_touch():
    try:
        while True:
            if GPIO.input(TOUCH_PIN) == GPIO.HIGH:
                time.sleep(3)  # Confirm a long press
                if GPIO.input(TOUCH_PIN) == GPIO.HIGH:
                    # Toggle recording service based on its current status
                    if waiting_to_restart:
                        # If in waiting period, start immediately
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
        print(f"Upload successful for {file_path} as {blob_name}")
        connection = sqlite3.connect(DATABASE_PATH)
        cursor = connection.cursor()
        cursor.execute('UPDATE files SET status = ? WHERE file_path = ?', ('uploaded', file_path))
        connection.commit()
        connection.close()
    except Exception as e:
        print(f"Failed to upload {file_path}: {e}")

def upload_worker():
    while True:
        # Connect to the database and fetch files in order of their timestamps (FIFO)
        connection = sqlite3.connect(DATABASE_PATH)
        cursor = connection.cursor()
        cursor.execute('SELECT file_path FROM files WHERE status = "to_upload" ORDER BY timestamp ASC')
        files_to_upload = cursor.fetchall()
        connection.close()

        # Attempt to upload each file in the order it was saved
        for (file_path,) in files_to_upload:
            if upload_file(file_path):  # If upload is successful
                # Mark the file as uploaded in the database
                connection = sqlite3.connect(DATABASE_PATH)
                cursor = connection.cursor()
                cursor.execute('UPDATE files SET status = ? WHERE file_path = ?', ('uploaded', file_path))
                connection.commit()
                connection.close()

        # Wait before checking for new files
        time.sleep(10)

# Set Timezone from Network
def get_timezone_from_ip():
    try:
        response = requests.get("https://ipapi.co/timezone")
        if response.status_code == 200:
            return response.text.strip()
    except Exception as e:
        print(f"Error fetching timezone: {e}")
    return None

def set_local_time():
    utc_timestamp = datetime.datetime.now(datetime.timezone.utc)
    timezone_str = get_timezone_from_ip()
    if timezone_str:
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
