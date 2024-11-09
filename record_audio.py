import pyaudio
import wave
import os
import datetime
import threading
import sqlite3

CHUNK = 48000
SAMP_RATE = 48000
FORMAT = pyaudio.paInt16
CHANNELS = 1
RECORD_DURATION = 10  # seconds
DATA_FOLDER = "./data"

def save_audio_buffer(buffer, start_time):
    # Create a local instance of pyaudio
    audio = pyaudio.PyAudio()
    date_folder = start_time.strftime('%Y-%m-%d')
    os.makedirs(os.path.join(DATA_FOLDER, date_folder), exist_ok=True)
    file_name = f"{start_time.strftime('%Y-%m-%d_%H_%M_%S')}.wav"
    file_path = os.path.join(DATA_FOLDER, date_folder, file_name)

    with wave.open(file_path, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(SAMP_RATE)
        wf.writeframes(b''.join(buffer))

    print(f"Saved audio file: {file_path}")

    # Close the local pyaudio instance
    audio.terminate()

    # Insert file path into database for upload tracking
    connection = sqlite3.connect('tracking.db')
    cursor = connection.cursor()
    cursor.execute('INSERT INTO files (file_path, status) VALUES (?, ?)', (file_path, 'to_upload'))
    connection.commit()
    connection.close()

def record_audio_continuously():
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, rate=SAMP_RATE, channels=CHANNELS, input=True, frames_per_buffer=CHUNK)

    buffer1 = []
    buffer2 = []
    active_buffer = buffer1

    print("Continuous recording started. Press Ctrl+C to stop.")
    try:
        while True:
            start_time = datetime.datetime.now()
            active_buffer.clear()
            for _ in range(0, int(SAMP_RATE / CHUNK * RECORD_DURATION)):
                data = stream.read(CHUNK, exception_on_overflow=False)
                active_buffer.append(data)

            # Pass the buffer to be saved
            buffer_to_save = active_buffer
            threading.Thread(target=save_audio_buffer, args=(buffer_to_save, start_time), daemon=True).start()
            active_buffer = buffer2 if active_buffer is buffer1 else buffer1

    except KeyboardInterrupt:
        print("\nRecording stopped by user.")
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

if __name__ == "__main__":
    record_audio_continuously()
