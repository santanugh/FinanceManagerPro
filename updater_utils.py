import requests
import os
import sys
import subprocess
import packaging.version
import logging

# --- CONFIGURATION ---
GITHUB_USER = "santanugh"
GITHUB_REPO = "FinanceManagerPro"
CURRENT_VERSION = "1.0.0"

def check_for_updates():
    """
    Returns:
        (None, None) if no update
        (download_url, tag_name) if update available
    """
    api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
    
    try:
        response = requests.get(api_url, timeout=5)
        if response.status_code != 200:
            return None, None
            
        data = response.json()
        latest_tag = data.get("tag_name", "v0.0.0")
        assets = data.get("assets", [])
        
        if not assets:
            return None, None
            
        # Get the download link for the .exe file
        download_url = assets[0].get("browser_download_url")
        
        # Compare Versions
        v_current = packaging.version.parse(CURRENT_VERSION)
        v_latest = packaging.version.parse(latest_tag.lstrip("v"))
        
        if v_latest > v_current:
            return download_url, latest_tag
            
    except Exception as e:
        logging.error(f"Update check failed: {e}")
        
    return None, None

def run_update_process(download_url):
    """Downloads the update and restarts the app."""
    try:
        logging.info("Downloading update...")
        # 1. Download the new EXE
        new_exe_name = "update_temp.exe"
        response = requests.get(download_url, stream=True)
        with open(new_exe_name, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        # 2. Define current EXE path
        current_exe = sys.executable
        
        # 3. Create the Batch script to swap files
        # We need a batch script because we can't delete the running EXE while it's open.
        bat_script = f"""
@echo off
echo Updating Finance Manager...
timeout /t 3 /nobreak > NUL
del "{current_exe}"
move "{new_exe_name}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
        with open("updater.bat", "w") as f:
            f.write(bat_script)
            
        # 4. Launch the batch file and kill this app
        subprocess.Popen(["updater.bat"], shell=True)
        sys.exit(0)
        
    except Exception as e:
        logging.error(f"Update installation failed: {e}")
        return False