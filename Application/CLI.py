import sys
import serial
from pathlib import Path
import matplotlib.pyplot as plt
from processing.processing import process_spectrum
from hardware.espComms import send_servo_command
from hardware.cameraControl import Camera

RAW_DIR = Path("preprocessing/spectra/raw")

scan_running = False  # global flag for scan status
cam = None  # global camera instance for debug mode

def list_raw_spectra(): #debugging
    """Return a list of CSV files in the raw spectra folder."""
    raw_files = [f.name for f in RAW_DIR.glob("*.csv")]
    return raw_files

def process_spectrum_cli():
    raw_files = list_raw_spectra()
    if not raw_files:
        print(f"No raw spectra found in {RAW_DIR}")
        return

    print("\nAvailable spectra:")
    for i, f in enumerate(raw_files):
        print(f"{i+1}: {f}")

    # Ask user which file to process
    while True:
        file_choice = input(f"Select a spectrum to process [1-{len(raw_files)}]: ").strip()
        if file_choice.isdigit() and 1 <= int(file_choice) <= len(raw_files):
            file_to_process = raw_files[int(file_choice)-1]
            break
        else:
            print("Invalid choice, try again.")

    print(f"\nProcessing '{file_to_process}'...\n")
    scan_running = True

    try:
        best_match, best_r, top3, x, y = process_spectrum(file_to_process, log_callback=print)
    except Exception as e:
        print(f"Error during processing: {e}")
        scan_running = False
        return

    # Display results
    print("\n=== Results ===")
    print(f"Best match: {best_match}, Pearson r = {best_r:.4f}")
    print("Top 3 matches:")
    for i, (mat, r_val) in enumerate(top3, 1):
        print(f"{i}. {mat}, Pearson r = {r_val:.4f}")

    # Plot processed spectrum
    plt.figure(figsize=(12,5))
    plt.plot(x, y, color="#2563eb")
    plt.xlabel("Wavenumber (cm⁻¹)")
    plt.ylabel("Normalized Intensity")
    plt.title(f"Processed Spectrum: {file_to_process}")
    plt.show()

def servo_test():
    print("Running servo test...")
    # Initialize serial connection
    try:
        ser = serial.Serial("/dev/ttyS0", 115200, timeout=2)
        print("Serial connection established on /dev/ttyS0 at 115200 baud")
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
        exit(1)
    
    #run test command
    send_servo_command(ser)

    #close serial connection
    ser.close()
    print("Serial connection closed")

def start_scan():
    global scan_running
    if scan_running:
        print("Scan already running!")
        return
    print("Starting scan...")
    scan_running = True

def stop_scan():
    global scan_running
    if scan_running:
        print("Stopping scan...")
        scan_running = False
    else:
        print("No scan is currently running.")

def exit_app():
    global scan_running
    if scan_running:
        print("Stopping running scan before exit...")
        scan_running = False
    print("Exiting ECOSpec CLI.")
    sys.exit(0)

def debug_mode():
    print("\n=== Debug Mode ===")
    print("Options:")
    print("1. Processing test")
    print("2. Servo Test")
    print("3. Camera Test")
    debugMode = input("Select a debug option [1-3]: ").strip()
    if debugMode == "1":
        print("Running processing test...")
        process_spectrum_cli()
    elif debugMode == "2":
        print("Running servo test...")
        servo_test()
    elif debugMode == "3":
        print("Running camera test...")
        global cam
        cam = Camera()
        print("Camera object made, initializing...")
        cam.init()
        print("Camera initialized, reading info...")
        cam.read_image_info()
        print("Fetching test image...")
        cam.get_test_image()
        print("Closing camera...")
        cam.close()
        print("Camera closed successfully.")

def main():
    while True:
        print("\n=== ECOSpec CLI ===")
        print("Options:")
        print("1. Start scan")
        print("2. Stop scan")
        print("3. Debug Mode")
        print("4. Exit")
        choice = input("Select an option [1-4]: ").strip()

        if choice == "1":
            start_scan()
        elif choice == "2":
            stop_scan()
        elif choice == "3":
            debug_mode()
        elif choice == "4":
            exit_app()
        else:
            print("Invalid option, try again.")

if __name__ == "__main__":
    main()