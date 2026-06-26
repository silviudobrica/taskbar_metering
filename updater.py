"""
Auto-update module for Taskbar Metering
Handles checking for new releases on GitHub and upgrading the application
"""

import os
import sys
import json
import urllib.request
import urllib.error
import logging
import subprocess
import shutil
import time
from pathlib import Path

import config

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com/repos/silviudobrica/taskbar_metering/releases/latest"
GITHUB_RELEASES_PAGE = "https://github.com/silviudobrica/taskbar_metering/releases"


def parse_version(version_str):
    """Parse version string like '1.1.0' into tuple for comparison"""
    try:
        return tuple(int(x) for x in version_str.strip('v').split('.'))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def is_newer_version_available():
    """Check if a newer version is available on GitHub"""
    try:
        with urllib.request.urlopen(GITHUB_API_URL, timeout=5) as response:
            data = json.loads(response.read().decode())
            latest_tag = data.get('tag_name', 'v1.0.0')
            latest_version = parse_version(latest_tag)
            current_version = parse_version(config.APP_VERSION)
            
            logger.debug(f"Current version: {current_version}, Latest: {latest_version}")
            return latest_version > current_version, latest_tag
    except Exception as e:
        logger.warning(f"Failed to check for updates: {e}")
        return False, None


def get_latest_release_info():
    """Get full release info from GitHub"""
    try:
        with urllib.request.urlopen(GITHUB_API_URL, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        logger.warning(f"Failed to fetch release info: {e}")
        return None


def download_exe(download_url, target_path):
    """Download the latest executable from GitHub"""
    try:
        logger.info(f"Downloading from {download_url}")
        urllib.request.urlretrieve(download_url, target_path)
        logger.info(f"Downloaded to {target_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to download: {e}")
        return False


def kill_running_instances():
    """Kill all running taskbar_meter processes"""
    try:
        # Use taskkill to terminate the process
        subprocess.run(
            ["taskkill", "/F", "/IM", "taskbar_meter.exe"],
            capture_output=True,
            timeout=5
        )
        logger.info("Killed running instances of taskbar_meter.exe")
        time.sleep(1)  # Give processes time to clean up
        return True
    except Exception as e:
        logger.warning(f"Failed to kill processes: {e}")
        return False


def backup_executable(exe_path):
    """Create a backup of the current executable"""
    try:
        backup_path = exe_path + ".bak"
        shutil.copy2(exe_path, backup_path)
        logger.info(f"Created backup at {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        return None


def replace_executable(old_path, new_path, backup_path=None):
    """Replace the old executable with the new one, with retry logic for locked files"""
    max_retries = 5
    retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            # Remove old executable
            if os.path.exists(old_path):
                os.remove(old_path)
            
            # Move new executable to target location
            shutil.move(new_path, old_path)
            logger.info(f"Successfully replaced executable at {old_path}")
            
            # Clean up backup if successful
            if backup_path and os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except Exception:
                    pass
            
            return True
        except PermissionError as e:
            if attempt < max_retries - 1:
                logger.warning(f"File locked, retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 1.5  # Exponential backoff
            else:
                logger.error(f"Failed to replace executable after {max_retries} attempts: {e}")
                # Restore backup if available
                if backup_path and os.path.exists(backup_path):
                    try:
                        shutil.copy2(backup_path, old_path)
                        logger.info("Restored backup after failed upgrade")
                    except Exception:
                        pass
                return False
        except Exception as e:
            logger.error(f"Unexpected error replacing executable: {e}")
            return False
    
    return False


def perform_upgrade():
    """
    Full upgrade workflow:
    1. Check for newer version
    2. Kill running instances
    3. Download new executable
    4. Backup current executable
    5. Replace with new version
    6. Restart application
    """
    try:
        logger.info("Starting upgrade process...")
        
        # Step 1: Check for newer version
        newer_available, latest_tag = is_newer_version_available()
        if not newer_available:
            logger.info("Already running latest version")
            return False, "Already running the latest version"
        
        logger.info(f"New version available: {latest_tag}")
        
        # Step 2: Get release info and find download URL
        release_info = get_latest_release_info()
        if not release_info:
            return False, "Failed to fetch release information"
        
        # Find the exe download URL
        download_url = None
        for asset in release_info.get('assets', []):
            if asset['name'] == 'taskbar_meter.exe':
                download_url = asset['browser_download_url']
                break
        
        if not download_url:
            return False, "No executable found in latest release"
        
        logger.info(f"Found download URL: {download_url}")
        
        # Step 3: Kill running instances
        kill_running_instances()
        
        # Step 4: Download new executable to temp location
        temp_dir = os.path.join(os.environ.get("TEMP"), "taskbar_meter_update")
        os.makedirs(temp_dir, exist_ok=True)
        temp_exe = os.path.join(temp_dir, "taskbar_meter_new.exe")
        
        if not download_exe(download_url, temp_exe):
            return False, "Failed to download update"
        
        # Step 5: Get current executable path
        current_exe = os.path.abspath(sys.argv[0])
        if not current_exe.endswith('.exe'):
            # If running from source, can't upgrade exe
            logger.warning("Running from source code, cannot upgrade exe")
            return False, "Cannot upgrade when running from source"
        
        # Step 6: Backup current executable
        backup_path = backup_executable(current_exe)
        
        # Step 7: Replace with new version
        if not replace_executable(current_exe, temp_exe, backup_path):
            return False, "Failed to install updated executable"
        
        logger.info("Upgrade completed successfully")
        
        # Step 8: Restart application
        try:
            subprocess.Popen([current_exe, "--run"])
        except Exception as e:
            logger.error(f"Failed to restart application: {e}")
        
        return True, f"Successfully upgraded to {latest_tag}"
        
    except Exception as e:
        logger.error(f"Upgrade failed: {e}")
        return False, f"Upgrade failed: {str(e)}"
