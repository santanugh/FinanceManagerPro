import requests
import os
import sys
import subprocess
import packaging.version
import logging
import time
import datetime

# --- CONFIGURATION ---
GITHUB_USER = "santanugh"
GITHUB_REPO = "FinanceManagerPro"
CURRENT_VERSION = "1.0.2" 

# --- SSL CERTIFICATE FIX FOR FROZEN APPS ---
def configure_ssl():
    """Forces requests to use the bundled certifi certificate inside the EXE."""
    if getattr(sys, 'frozen', False):
        # We are running in a bundle
        base_path = sys._MEIPASS
        # Look for the certificate file bundled by --collect-all certifi
        cert_path = os.path.join(base_path, 'certifi', 'cacert.pem')
        if os.path.exists(cert_path):
            os.environ['REQUESTS_CA_BUNDLE'] = cert_path

# Run this immediately
configure_ssl()

def check_for_updates():
    api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
    try:
        headers = {'User-Agent': 'FinanceManagerPro'}
        # SECURE CHECK
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code != 200: return None, None
        
        data = response.json()
        latest_tag = data.get("tag_name", "v0.0.0")
        assets = data.get("assets", [])
        
        if not assets: return None, None
        
        download_url = ""
        expected_size = 0
        for asset in assets:
            if asset["name"].lower().endswith(".exe"):
                download_url = asset["browser_download_url"]
                expected_size = asset["size"]
                break
        
        if not download_url: return None, None

        v_current = packaging.version.parse(CURRENT_VERSION)
        v_latest = packaging.version.parse(latest_tag.lstrip("v"))
        
        if v_latest > v_current:
            return download_url, latest_tag, expected_size
    except:
        pass
    return None, None

def download_update(download_url, expected_size, progress_callback=None):
    new_exe_name = "update_temp.exe"
    if os.path.exists(new_exe_name):
        try: os.remove(new_exe_name)
        except: pass

    try:
        headers = {'User-Agent': 'FinanceManagerPro'}
        # SECURE DOWNLOAD
        response = requests.get(download_url, headers=headers, stream=True, timeout=30)
        
        downloaded_size = 0
        
        with open(new_exe_name, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    
                    if expected_size > 0 and progress_callback:
                        percent = downloaded_size / expected_size
                        progress_callback(percent)

        if os.path.exists(new_exe_name):
            actual_size = os.path.getsize(new_exe_name)
            if expected_size > 0 and abs(actual_size - expected_size) > 1024:
                logging.error(f"Size Mismatch! Expected {expected_size}, got {actual_size}")
                return False
            return True
        return False
    except Exception as e:
        logging.error(f"Download Error: {e}")
        return False

def install_update():
    new_exe_name = "update_temp.exe"
    current_exe = os.path.abspath(sys.executable)
    exe_name = os.path.basename(current_exe)
    
    log_dir = "update_logs"
    if not os.path.exists(log_dir): os.makedirs(log_dir)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.abspath(os.path.join(log_dir, f"install_{timestamp}.txt"))

    bat_script = f"""
@echo off
echo [INFO] Script Started > "{log_file}"
echo [INFO] Waiting for {exe_name} to close... >> "{log_file}"
timeout /t 3 >> "{log_file}"

echo [INFO] Killing process... >> "{log_file}"
taskkill /F /IM "{exe_name}" >> "{log_file}" 2>&1
taskkill /F /IM "flet.exe" >> "{log_file}" 2>&1

echo [INFO] Deleting old file... >> "{log_file}"
:DEL_LOOP
del "{exe_name}" >> "{log_file}" 2>&1
if exist "{exe_name}" (
    echo [RETRY] File locked, waiting... >> "{log_file}"
    timeout /t 1 >> "{log_file}"
    goto DEL_LOOP
)

echo [INFO] Swapping files... >> "{log_file}"
move "{new_exe_name}" "{exe_name}" >> "{log_file}" 2>&1

echo [INFO] Restarting App... >> "{log_file}"
start "" "{exe_name}"
echo [INFO] Done. >> "{log_file}"
del "%~f0"
"""
    with open("updater.bat", "w") as f:
        f.write(bat_script)
    
    try:
        os.startfile("updater.bat")
    except:
        pass