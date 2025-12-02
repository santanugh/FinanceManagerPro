import tkinter as tk
from tkinter import ttk
import sys
import os
import time
import threading
import requests
import subprocess
import datetime
import ctypes

# --- RESOURCE PATH HELPER (Debugged) ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

# --- SETUP LOGGING ---
log_dir = "updater_logs"
if not os.path.exists(log_dir):
    try: os.makedirs(log_dir)
    except: pass

timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = os.path.join(log_dir, f"update_{timestamp}.txt")

def log(message):
    try:
        with open(log_file, "a") as f:
            f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}\n")
    except: pass

log("--- UPDATER STARTED (TKINTER) ---")

class UpdaterApp:
    def __init__(self, root, url, version, target_exe):
        self.root = root
        self.url = url
        self.version = version
        self.target_exe = target_exe
        self.exe_name = os.path.basename(target_exe)
        
        # WINDOW SETUP
        self.root.title("System Update")
        self.root.geometry("350x150")
        self.root.resizable(False, False)
        self.root.configure(bg="#2C2C2C")
        
        # --- ICON LOADING (Verbose Debugging) ---
        icon_path = resource_path("download.ico")
        log(f"Looking for icon at: {icon_path}")
        
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
                log("Icon loaded successfully.")
            except Exception as e:
                log(f"Icon Load Failed (Tkinter Error): {e}")
        else:
            log("Icon file NOT FOUND in bundled resources.")

        # Center Window
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - 350) // 2
        y = (screen_height - 150) // 2
        self.root.geometry(f"350x150+{x}+{y}")

        # UI ELEMENTS
        self.lbl_title = tk.Label(root, text=f"Updating to {version}...", font=("Segoe UI", 12, "bold"), fg="white", bg="#2C2C2C")
        self.lbl_title.pack(pady=(20, 10))

        style = ttk.Style()
        style.theme_use('default')
        style.configure("green.Horizontal.TProgressbar", background='#00E676', thickness=20)
        
        self.progress = ttk.Progressbar(root, style="green.Horizontal.TProgressbar", orient="horizontal", length=280, mode="determinate")
        self.progress.pack(pady=5)

        self.lbl_status = tk.Label(root, text="Initializing...", font=("Segoe UI", 9), fg="lightgray", bg="#2C2C2C")
        self.lbl_status.pack(pady=5)

        # Start Logic
        threading.Thread(target=self.run_update, daemon=True).start()

    def update_status(self, text, color="lightgray"):
        self.lbl_status.config(text=text, fg=color)

    def run_update(self):
        temp_file = "update_temp.exe"

        # 1. KILL OLD APP
        self.update_status("Closing application...")
        log(f"Killing {self.exe_name}...")
        subprocess.run(f'taskkill /F /IM "{self.exe_name}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)

        # 2. DOWNLOAD
        try:
            self.update_status("Downloading...")
            log(f"Downloading from {self.url}")
            
            headers = {'User-Agent': 'FinanceManagerPro'}
            response = requests.get(self.url, headers=headers, stream=True, timeout=30)
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(temp_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            self.progress['value'] = percent
            
            log("Download complete.")
        except Exception as e:
            log(f"Download Error: {e}")
            self.update_status("Download Failed", "red")
            time.sleep(3)
            os._exit(1)

        # 3. SWAP
        self.update_status("Installing...")
        log("Swapping files...")
        
        swap_success = False
        for i in range(10):
            try:
                if os.path.exists(self.target_exe):
                    os.remove(self.target_exe)
                if os.path.exists(temp_file):
                    os.rename(temp_file, self.target_exe)
                swap_success = True
                break
            except Exception as e:
                log(f"Retry {i}: {e}")
                self.update_status(f"Retrying install ({i+1}/10)...")
                time.sleep(1)
                subprocess.run(f'taskkill /F /IM "{self.exe_name}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not swap_success:
            self.update_status("File Locked. Please Restart PC.", "red")
            log("Critical Swap Failure.")
            time.sleep(5)
            os._exit(1)

        # 4. RESTART
        self.update_status("Done! Restarting...", "#66BB6A") # Green
        self.progress['value'] = 100
        log("Restarting Main App...")
        time.sleep(2)
        
        try:
            subprocess.Popen([self.target_exe], close_fds=True, creationflags=0x00000008)
        except Exception as e:
            log(f"Launch Error: {e}")

        log("Exiting.")
        os._exit(0)

if __name__ == "__main__":
    try:
        # ARGUMENTS
        try:
            url_arg = sys.argv[1]
            ver_arg = sys.argv[2]
            tgt_arg = sys.argv[3]
        except:
            url_arg = ""
            ver_arg = "Unknown"
            tgt_arg = "FinanceManagerPro.exe"

        root = tk.Tk()
        app = UpdaterApp(root, url_arg, ver_arg, tgt_arg)
        root.mainloop()
    except Exception as e:
        log(f"CRASH: {e}")