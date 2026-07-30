# run_dashboard.py

import os
import sys
import subprocess


def check_streamlit_installed() -> bool:
    """
    Checks if the Streamlit package is installed in the active environment.
    """
    try:
        import streamlit
        return True
    except ImportError:
        return False


def main():
    dashboard_path = os.path.join("dashboard", "app.py")
    
    # 1. Verify dashboard app exists
    if not os.path.exists(dashboard_path):
        print(f"[-] Dashboard application file not found at: {dashboard_path}")
        print("    Please ensure you have saved the previous dashboard/app.py file first.")
        sys.exit(1)

    # 2. Verify Streamlit dependency
    if not check_streamlit_installed():
        print("[-] Streamlit is not installed in the active Python environment.")
        print("    Please install Streamlit to run the visual analytics dashboard:")
        print("    pip install streamlit")
        sys.exit(1)

    print("[+] Launching Quantoryx local Analytics Dashboard...")
    print(f"    - Running: streamlit run {dashboard_path}")
    print("    - Press Ctrl+C in this terminal window to stop the server.")

    # 3. Start Streamlit server
    try:
        subprocess.run(["streamlit", "run", dashboard_path], check=True)
    except KeyboardInterrupt:
        print("\n[+] Dashboard server stopped by user.")
    except Exception as e:
        print(f"[-] Failed to launch Streamlit server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
