import RPi.GPIO as GPIO
import time
import subprocess
import threading

# GPIO setup TESTING 1
TOUCH_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(TOUCH_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)  # Use pull-down to stabilize input

# State variables
recording_process = None
waiting_for_restart = False  # Flag to track the 1-hour wait period

# Start `upload_to_cloud.py` and `delete_uploaded_files.py` as continuous background processes
def start_background_processes():
    subprocess.Popen(["python3", "/home/pr/TEST/upload_to_cloud.py"])
    subprocess.Popen(["python3", "/home/pr/TEST/delete_uploaded_files.py"])
    print("Started upload and delete processes.")

# Start recording with `record_audio.py`
def start_recording():
    global recording_process, waiting_for_restart
    if recording_process is None:
        print("Starting recording...")
        recording_process = subprocess.Popen(["python3", "/home/pr/TEST/record_audio.py"])
        waiting_for_restart = False

# Stop recording with `record_audio.py`
def stop_recording():
    global recording_process
    if recording_process:
        print("Stopping recording...")
        recording_process.terminate()
        recording_process = None

# Function to wait for 1 hour before restarting recording
def wait_and_restart_recording():
    global waiting_for_restart
    waiting_for_restart = True
    print("Waiting for 1 hour to restart recording...")
    time.sleep(3600)  # 1 hour in seconds
    if waiting_for_restart:  # Check if still waiting after 1 hour
        start_recording()

# Touch button handler with debugging and debounce
def handle_touch_press():
    global waiting_for_restart

    # Start timing the press duration
    touch_start_time = time.time()
    while GPIO.input(TOUCH_PIN) == GPIO.HIGH:
        press_duration = time.time() - touch_start_time
        if press_duration >= 3:  # 3-second hold detected
            if recording_process:  # If recording, stop it and wait for 1 hour
                print("Detected long press. Stopping recording.")
                stop_recording()
                threading.Thread(target=wait_and_restart_recording, daemon=True).start()
            elif waiting_for_restart:  # If waiting, restart recording immediately
                print("Detected long press during wait period. Restarting recording immediately.")
                waiting_for_restart = False
                start_recording()
            break  # Exit loop after handling the press
        time.sleep(0.1)

if __name__ == "__main__":
    # Start upload and delete processes (they will continue running in the background)
    start_background_processes()

    # Start recording initially
    start_recording()

    try:
        while True:
            if GPIO.input(TOUCH_PIN) == GPIO.HIGH:  # Button is pressed
                print("Touch detected. Checking for long press...")
                handle_touch_press()
            time.sleep(0.1)  # Polling delay to reduce CPU usage

    except KeyboardInterrupt:
        print("Script interrupted. Cleaning up...")
    finally:
        # Cleanup GPIO and ensure the recording process is terminated on exit
        GPIO.cleanup()
        if recording_process:
            recording_process.terminate()
