import os
import time
import shutil
from azure.iot.device import IoTHubDeviceClient
from azure.storage.blob import BlobClient
from concurrent.futures import ThreadPoolExecutor, as_completed

# Constants
CONNECTION_STRING = "HostName=PRESAGE.azure-devices.net;DeviceId=trial2;SharedAccessKey=ZIzS38C3pnhtudEMoadfX5q/MOz/wVQaArjcF+sZtJQ="
DATA_FOLDER = "./data"
MAX_CONCURRENT_UPLOADS = 5

# Function to extract Device ID from the connection string
def get_device_id(connection_string):
    parts = connection_string.split(";")
    for part in parts:
        if part.startswith("DeviceId="):
            return part.split("=")[1]
    return "UnknownDevice"

# Extract Device ID
DEVICE_ID = get_device_id(CONNECTION_STRING)

device_client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING, websockets=True)
device_client.connect()

def move_to_uploaded(file_path):
    date_folder = os.path.dirname(os.path.dirname(file_path))
    uploaded_folder = os.path.join(date_folder, "Uploaded")
    os.makedirs(uploaded_folder, exist_ok=True)
    new_path = os.path.join(uploaded_folder, os.path.basename(file_path))
    shutil.move(file_path, new_path)
    print(f"Moved {file_path} to {new_path}")

def upload_file(file_path):
    # Check if DEVICE_ID is already part of the filename
    file_name = os.path.basename(file_path)
    if DEVICE_ID not in file_name:
        # Insert DEVICE_ID into the filename before uploading
        file_dir = os.path.dirname(file_path)
        new_file_name = f"{DEVICE_ID}_{file_name}"
        new_file_path = os.path.join(file_dir, new_file_name)
        os.rename(file_path, new_file_path)  # Rename the file locally
        file_path = new_file_path
        print(f"Renamed file to include device ID: {file_path}")

    blob_name = os.path.relpath(file_path, "./data")  # Adjust blob name for Azure
    try:
        blob_info = device_client.get_storage_info_for_blob(blob_name)
        sas_url = f"https://{blob_info['hostName']}/{blob_info['containerName']}/{blob_info['blobName']}{blob_info['sasToken']}"
        
        with BlobClient.from_blob_url(sas_url) as blob_client, open(file_path, "rb") as file:
            blob_client.upload_blob(file, overwrite=True)
        device_client.notify_blob_upload_status(blob_info["correlationId"], True, 200, "Upload successful.")
        print(f"Uploaded: {file_path}")
        
        move_to_uploaded(file_path)
    except Exception as e:
        print(f"Failed to upload {file_path}: {e}")

def upload_files_concurrently():
    while True:
        for date_folder in os.listdir(DATA_FOLDER):
            to_upload_folder = os.path.join(DATA_FOLDER, date_folder, "To upload")
            if os.path.isdir(to_upload_folder):
                files_to_upload = sorted(
                    [os.path.join(to_upload_folder, f) for f in os.listdir(to_upload_folder)],
                    key=os.path.getctime
                )
                
                with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_UPLOADS) as executor:
                    future_to_file = {executor.submit(upload_file, file_path): file_path for file_path in files_to_upload}
                    
                    for future in as_completed(future_to_file):
                        try:
                            future.result()
                        except Exception as e:
                            print(f"Error uploading file: {e}")

        time.sleep(10)

if __name__ == "__main__":
    print(f"Using DEVICE_ID: {DEVICE_ID}")
    upload_files_concurrently()
