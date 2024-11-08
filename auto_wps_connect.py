import subprocess
import time
import re

def connect_via_wps():
    print("Attempting to connect via WPS...")

    # Start the WPS connection process
    try:
        # Initiate WPS push-button connect
        subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "wps_pbc"], check=True)
        print("WPS initiated. Press the WPS button on your router within 2 minutes.")
        
        # Wait and check for connection
        connected = False
        for _ in range(15):  # Wait for up to 1.5 minutes, checking every 10 seconds
            time.sleep(10)
            
            # Check connection status
            iwconfig_output = subprocess.check_output(["iwconfig", "wlan0"]).decode("utf-8")
            if "ESSID" in iwconfig_output and "off/any" not in iwconfig_output:
                print("Connected to Wi-Fi network.")
                connected = True
                break

        if not connected:
            print("Failed to connect within the time limit. Please try again.")
            return False

        # Get IP address to confirm network connection
        ip_output = subprocess.check_output(["ifconfig", "wlan0"]).decode("utf-8")
        ip_address = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', ip_output)
        if ip_address:
            print(f"Connected successfully with IP address: {ip_address.group(1)}")
            return True
        else:
            print("Connected to Wi-Fi, but failed to obtain an IP address.")
            return False

    except subprocess.CalledProcessError as e:
        print(f"Error during WPS connection: {e}")
        return False

# Run the script
if __name__ == "__main__":
    success = connect_via_wps()
    if success:
        print("Automatic WPS connection established.")
    else:
        print("Automatic WPS connection failed.")
