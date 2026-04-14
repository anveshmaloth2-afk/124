import subprocess
import time
import os
from flask import Flask
from threading import Thread

# --- WEB SERVER TO KEEP RENDER AWAKE ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web_server():
    # Render uses the PORT environment variable automatically
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web_server)
    t.start()
# ---------------------------------------

def restart_bot():
    while True:
        try:
            # Get the path to your paid.py file
            current_directory = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(current_directory, 'paid.py')
            
            print(f"Starting bot: {script_path}")
            # Runs your actual bot script
            subprocess.run(['python3', script_path], check=True)
            
        except subprocess.CalledProcessError as e:
            print(f"Bot crashed with error: {e}. Restarting in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            time.sleep(5)

if __name__ == "__main__":
    keep_alive()  # Starts the background web server
    restart_bot() # Starts the infinite loop for your bot
