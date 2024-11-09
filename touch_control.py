import RPi.GPIO as GPIO
import time
import subprocess

TOUCH_PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(TOUCH_PIN, GPIO.IN)

recording_service = "record_audio.service"

def start_recording():
    print("Starting recording service...")
    subprocess.run(["sudo", "systemctl", "start", recording_service])

def stop_recording():
    print("Stopping recording service for 1 hour...")
    subprocess.run(["sudo", "systemctl", "stop", recording_service])
    time.sleep(3600)  # Wait for 1 hour before restarting
    start_recording()

try:
    while True:
        if GPIO.input(TOUCH_PIN) == GPIO.HIGH:
            time.sleep(3)  # Wait for 3 seconds to confirm a long press
            if GPIO.input(TOUCH_PIN) == GPIO.HIGH:
                if subprocess.run(["systemctl", "is-active", "--quiet", recording_service]).returncode == 0:
                    stop_recording()  # Stop if it's running
                else:
                    start_recording()  # Start if it's not running
except KeyboardInterrupt:
    print("Exiting touch control...")
finally:
    GPIO.cleanup()
