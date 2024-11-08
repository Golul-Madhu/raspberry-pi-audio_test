import pyaudio
import wave
import os
import datetime
import threading

# Audio recording parameters
CHUNK = 48000
SAMP_RATE = 48000
FORMAT = pyaudio.paInt16
CHANNELS = 1
RECORD_DURATION = 10  # in seconds
DATA_FOLDER = "./data"

def save_audio_buffer(buffer, start_time):
    # Create a local instance of pyaudio to avoid undefined variable issues
    audio = pyaudio.PyAudio()
    
    date_folder = start_time.strftime('%Y-%m-%d')
    to_upload_folder = os.path.join(DATA_FOLDER, date_folder, "To upload")
    os.makedirs(to_upload_folder, exist_ok=True)
    
    end_time = datetime.datetime.now()
    file_name = f"{start_time.strftime('%Y-%m-%d')}_____{start_time.strftime('%H_%M_%S')}_to_{end_time.strftime('%H_%M_%S')}.wav"
    file_path = os.path.join(to_upload_folder, file_name)
    
    with wave.open(file_path, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(SAMP_RATE)
        wf.writeframes(b''.join(buffer))
    
    print(f"Saved audio file: {file_path}")
    
    # Close the local pyaudio instance
    audio.terminate()

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
            for _ in range(0, int(SAMP_RATE / CHUNK * RECORD_DURATION)):
                data = stream.read(CHUNK, exception_on_overflow=False)
                active_buffer.append(data)
            
            buffer_to_save = active_buffer
            active_buffer = buffer2 if active_buffer is buffer1 else buffer1
            # Pass the buffer to be saved to the `save_audio_buffer` function
            threading.Thread(target=save_audio_buffer, args=(buffer_to_save, start_time), daemon=True).start()
            active_buffer.clear()

    except KeyboardInterrupt:
        print("\nRecording stopped by user.")
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

if __name__ == "__main__":
    record_audio_continuously()
