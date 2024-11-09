import os
import time
import sqlite3
from azure.iot.device import IoTHubDeviceClient
from azure.storage.blob import BlobClient
DATABASE_PATH = "/home/pr/TEST/tracking.db"


# Connection string for Azure IoT
CONNECTION_STRING = "HostName=PRESAGE.azure-devices.net;DeviceId=trial2;SharedAccessKey=ZIzS38C3pnhtudEMoadfX5q/MOz/wVQaArjcF+sZtJQ="
device_client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING, websockets=True)

# Extract Device ID from the connection string for file naming
device_id = CONNECTION_STRING.split("DeviceId=")[1].split(";")[0]

def upload_file(file_path):
    try:
        # Append the device ID to the blob name for Azure Blob Storage
        original_blob_name = os.path.basename(file_path)
        blob_name = f"{device_id}_{original_blob_name}"  # Device ID added to blob name
        
        # Retrieve SAS token and upload to Azure Blob
        blob_info = device_client.get_storage_info_for_blob(blob_name)
        sas_url = f"https://{blob_info['hostName']}/{blob_info['containerName']}/{blob_info['blobName']}{blob_info['sasToken']}"

        # Upload the file
        with BlobClient.from_blob_url(sas_url) as blob_client, open(file_path, "rb") as file:
            blob_client.upload_blob(file, overwrite=True)
        device_client.notify_blob_upload_status(blob_info["correlationId"], True, 200, "Upload successful.")
        print(f"Upload successful for {file_path} as {blob_name}")

        # Update the database to mark the file as uploaded
        connection = sqlite3.connect(DATABASE_PATH)
        cursor = connection.cursor()
        cursor.execute('UPDATE files SET status = ? WHERE file_path = ?', ('uploaded', file_path))
        connection.commit()
        connection.close()

    except Exception as e:
        print(f"Failed to upload {file_path}: {e}")

def upload_worker():
    while True:
        connection = sqlite3.connect(DATABASE_PATH)
        cursor = connection.cursor()
        cursor.execute('SELECT file_path FROM files WHERE status = "to_upload"')
        files_to_upload = cursor.fetchall()
        connection.close()

        if files_to_upload:
            for (file_path,) in files_to_upload:
                upload_file(file_path)

        time.sleep(10)  # Check every 10 seconds for new files

if __name__ == "__main__":
    upload_worker()
