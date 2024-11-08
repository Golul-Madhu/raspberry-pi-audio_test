import os
import datetime
import time
import shutil

DATA_FOLDER = "./data"

def get_old_uploaded_folders():
    current_date = datetime.datetime.now().strftime('%Y-%m-%d')
    old_folders = []
    for folder_name in os.listdir(DATA_FOLDER):
        folder_path = os.path.join(DATA_FOLDER, folder_name)
        if os.path.isdir(folder_path) and folder_name != current_date:
            uploaded_folder = os.path.join(folder_path, "Uploaded")
            if os.path.isdir(uploaded_folder):
                old_folders.append(uploaded_folder)
    return old_folders

def delete_folder(folder_path):
    shutil.rmtree(folder_path)
    print(f"Deleted folder: {folder_path}")

if __name__ == "__main__":
    while True:
        old_folders = get_old_uploaded_folders()
        for folder_path in old_folders:
            delete_folder(folder_path)
        time.sleep(3600)  # Run every hour
