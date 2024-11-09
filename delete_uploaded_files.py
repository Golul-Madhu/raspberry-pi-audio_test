import os
import time
import sqlite3
import datetime

def delete_old_uploaded_files():
    while True:
        current_time = datetime.datetime.now()
        connection = sqlite3.connect('tracking.db')
        cursor = connection.cursor()
        cursor.execute('SELECT file_path, timestamp FROM files WHERE status = "uploaded"')
        uploaded_files = cursor.fetchall()
        
        for file_path, timestamp in uploaded_files:
            file_time = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            if (current_time - file_time).days >= 1:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Deleted file: {file_path}")

        time.sleep(3600)  # Run the deletion check every hour

if __name__ == "__main__":
    delete_old_uploaded_files()
