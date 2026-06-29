import subprocess
import sys
import socket
import os

def is_port_in_use(port: int) -> bool:
    """Checks if a local port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def kill_process_on_port(port: int):
    """Terminates any process currently listening on the specified port on Windows."""
    if not is_port_in_use(port):
        return
    
    print(f"Port {port} is currently in use. Cleaning up stale zombie processes...")
    try:
        # Find PIDs listening on this port using netstat
        cmd = f"netstat -ano | findstr LISTENING | findstr :{port}"
        output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
        
        pids_to_kill = set()
        for line in output.strip().split('\n'):
            parts = line.strip().split()
            if len(parts) >= 5:
                pid = parts[-1]
                pids_to_kill.add(pid)
                
        for pid in pids_to_kill:
            if pid != '0':
                print(f"Killing zombie process with PID: {pid}")
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Could not automatically clean up port {port}: {e}")

if __name__ == "__main__":
    # Clean up port 8501 (default Streamlit port)
    kill_process_on_port(8501)
    
    print("Launching Streamlit application...")
    try:
        # Spawn Streamlit as a subprocess
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])
    except KeyboardInterrupt:
        print("\nTerminated launcher. cleaning up...")
        kill_process_on_port(8501)
