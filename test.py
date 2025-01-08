import subprocess

# Replace with your actual values
github_username = "gokulchiral@gmail.com"
github_token = "YOUR_PERSONAL_ACCESS_TOKEN"  # Replace with your actual PAT
repository_url = "https://github.com/Golul-Madhu/raspberry-pi-audio_test.git"

# The file to be pushed
file_to_push = "hello.txt"

# Step 1: Configure git credentials for authentication
subprocess.run(f"git config --global user.name {github_username}", shell=True)
subprocess.run(f"git config --global user.email {github_username}", shell=True)

# Step 2: Add the file to staging
subprocess.run(f"git add {file_to_push}", shell=True)

# Step 3: Commit the changes
commit_message = "Automated commit for hello.txt"
subprocess.run(f"git commit -m \"{commit_message}\"", shell=True)

# Step 4: Set the remote URL with authentication (using PAT)
subprocess.run(f"git remote set-url origin https://{github_username}:{github_token}@github.com/Golul-Madhu/raspberry-pi-audio_test.git", shell=True)

# Step 5: Push the changes to GitHub
subprocess.run("git push origin main", shell=True)
