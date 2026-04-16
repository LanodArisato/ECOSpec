#!/usr/bin/env python3
"""
ECOSpec - Raspberry Pi 5 Native App Launcher
Integrated with Raman processing pipeline.
"""

import webview
import os
import sys
import glob
import serial
from hardware.cameraControl import Camera
from hardware.espComms import espComms
from processing.processing import process_spectrum

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
RAMAN_ROOT = BASE_DIR
HTML_PATH  = os.path.join(BASE_DIR, 'ui', 'index.html')
RAW_DIR    = os.path.join(BASE_DIR, 'processing', 'spectra', 'raw')

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if RAMAN_ROOT not in sys.path:
    sys.path.insert(0, RAMAN_ROOT)


class EcoSpecAPI:

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    # Hardware Detection
    def detect_hardware(self):
        result = {}

        esp32_ports = ['/dev/ttyS0'] + glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
        found_port  = next((p for p in esp32_ports if os.path.exists(p)), None)
        if found_port:
            result['esp32'] = {'status': 'ONLINE', 'cls': 'ok', 'detail': found_port}
        else:
            result['esp32'] = {'status': 'NOT FOUND', 'cls': 'warn', 'detail': None}

        camera_found = False
        try:
            cam = Camera()
            camera_found = cam.init()
            cam.reset()
        except Exception:
            camera_found = False

        if camera_found:
            result['camera'] = {'status': 'LINKED', 'cls': 'ok', 'detail': 'ACUROS CQD'}
        else:
            result['camera'] = {'status': 'NOT FOUND', 'cls': 'warn', 'detail': None}

        return result

    # Full Scan Pipeline 
    def run_scan(self):
        esp = espComms('/dev/ttyS0')

        if esp.ser is None:
            return {'ok': False, 'error': 'ESP32 connection error'}
        esp.send_servo_command(1) # Start door closure

        cam = Camera()
        cam.init()
        cam.get_test_image()
        cam.close()

        raw_files = sorted(
            glob.glob(os.path.join(RAW_DIR, '*.csv')),
            key=os.path.getmtime,
            reverse=True
        )
        if not raw_files:
            return {'ok': False, 'error': 'No raw spectrum file found after capture'}

        latest_file = os.path.basename(raw_files[0])

        best_match, best_r, top3, x, y = process_spectrum(
            latest_file,
            log_callback=None
        )

        y_list = list(y)
        mn, mx = min(y_list), max(y_list)
        y_norm = [(v - mn) / (mx - mn) for v in y_list] if mx - mn > 1e-9 else [0.0] * len(y_list)
        matches = [{'name': name, 'r': round(float(r_val), 4)} for name, r_val in top3]

        return {
            'ok':      True,
            'spectrum': y_norm,
            'shifts':  [int(v) for v in x],
            'match':   best_match,
            'r':       round(float(best_r), 4),
            'matches': matches,
            'file':    latest_file,
        }

    # ── Debug Scan ────────────────────────────────────────────────
    def debug_scan(self, filename):
        raw_path = os.path.join(RAW_DIR, filename)
        if not os.path.exists(raw_path):
            available = [os.path.basename(f) for f in glob.glob(os.path.join(RAW_DIR, '*.csv'))]
            return {'ok': False, 'error': f'File not found: {filename}', 'available': available}

        best_match, best_r, top3, x, y = process_spectrum(
            filename,
            log_callback=None
        )

        y_list = list(y)
        mn, mx = min(y_list), max(y_list)
        y_norm = [(v - mn) / (mx - mn) for v in y_list] if mx - mn > 1e-9 else [0.0] * len(y_list)
        matches = [{'name': name, 'r': round(float(r_val), 4)} for name, r_val in top3]

        return {
            'ok':      True,
            'spectrum': y_norm,
            'shifts':  [int(v) for v in x],
            'match':   best_match,
            'r':       round(float(best_r), 4),
            'matches': matches,
            'file':    filename,
            'debug':   True,
        }

    # List Raw Files 
    def list_raw_files(self):
        files = [os.path.basename(f) for f in glob.glob(os.path.join(RAW_DIR, '*.csv'))]
        return sorted(files)

    # CSV Export
    def save_csv(self, csv_text, full_path):
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(csv_text)
            return {'ok': True, 'path': full_path}
        except Exception as e:
            return {'ok': False, 'error': str(e)}


def main():
    api = EcoSpecAPI()

    window = webview.create_window(
    title='ECOSpec',
    url=f'file://{HTML_PATH}',
    width=1024,
    height=600,
    resizable=False,
    fullscreen=False,
    frameless=False,
    min_size=(1024, 600),
    background_color='#0a0e14',
    text_select=False,
    confirm_close=False,
    on_top=False,
    js_api=api,
)

    api.set_window(window)

    webview.start(
    debug=False,
    gui='gtk',
    http_server=False,
)


if __name__ == '__main__':
    main()
