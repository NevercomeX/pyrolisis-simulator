#!/usr/bin/env python3
import sys
import subprocess
import os
from pathlib import Path

# Force UTF-8 stdout encoding if possible to support symbols on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_update():
    # Ensure working directory is project root
    project_dir = Path(__file__).parent.resolve()
    os.chdir(project_dir)

    print("==================================================")
    print(" [UPDATE] Pyrolysis Simulator - Update & Setup Script")
    print("==================================================")

    # Step 1: Git Pull
    print("\n[1/2] Fetching and pulling latest updates from repository...")
    try:
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout.strip() if result.stdout else "Already up to date.")
        if result.stderr and result.stderr.strip():
            print(result.stderr.strip())
        print("[OK] Git pull finished successfully.")
    except FileNotFoundError:
        print("[ERROR] 'git' command not found. Please ensure Git is installed and added to PATH.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git pull failed with exit code {e.returncode}:")
        if e.stdout:
            print(e.stdout.strip())
        if e.stderr:
            print(e.stderr.strip())
        sys.exit(1)

    # Step 2: Install dependencies
    req_file = project_dir / "requirements.txt"
    print("\n[2/2] Installing / updating Python dependencies...")
    if req_file.exists():
        # Check for virtual environment in project folder
        venv_pip = project_dir / ".venv" / "Scripts" / "pip.exe"
        if not venv_pip.exists():
            venv_pip = project_dir / "venv" / "Scripts" / "pip.exe"
        if not venv_pip.exists():
            venv_pip = project_dir / ".venv" / "bin" / "pip"
        if not venv_pip.exists():
            venv_pip = project_dir / "venv" / "bin" / "pip"

        if venv_pip.exists():
            print(f"Using virtual environment pip: {venv_pip}")
            pip_cmd = [str(venv_pip), "install", "-r", str(req_file)]
        else:
            print(f"Using current Python executable: {sys.executable}")
            pip_cmd = [sys.executable, "-m", "pip", "install", "-r", str(req_file)]

        try:
            subprocess.run(pip_cmd, check=True)
            print("[OK] Dependencies updated successfully.")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Installing dependencies failed with exit code {e.returncode}.")
            sys.exit(1)
    else:
        print("[WARNING] requirements.txt was not found. Skipping dependency installation.")

    # Step 3: Restart systemd service if available (Linux server)
    if sys.platform != "win32":
        print("\n[3/3] Restarting systemd service 'pyrolysis'...")
        try:
            # Check if systemctl exists
            check_sysctl = subprocess.run(["which", "systemctl"], capture_output=True)
            if check_sysctl.returncode == 0:
                res = subprocess.run(["systemctl", "restart", "pyrolysis"], capture_output=True, text=True)
                if res.returncode == 0:
                    print("[OK] Service 'pyrolysis' restarted successfully.")
                else:
                    # Fallback with sudo if permission denied or non-root user
                    res_sudo = subprocess.run(["sudo", "systemctl", "restart", "pyrolysis"], capture_output=True, text=True)
                    if res_sudo.returncode == 0:
                        print("[OK] Service 'pyrolysis' restarted successfully (via sudo).")
                    else:
                        print(f"[WARNING] Could not restart 'pyrolysis' service: {res.stderr.strip() or res_sudo.stderr.strip()}")
            else:
                print("[INFO] 'systemctl' not found. Skipping service restart.")
        except Exception as e:
            print(f"[WARNING] Service restart skipped: {e}")

    print("\n==================================================")
    print(" [SUCCESS] Update completed successfully!")
    print("==================================================")

if __name__ == "__main__":
    run_update()
