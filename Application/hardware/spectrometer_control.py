import os
from sys import exit
from datetime import datetime
import csv
from oceandirect.OceanDirectAPI import OceanDirectAPI

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, 'processing', 'spectra', 'raw')

class Spectrometer:
    def __init__(self, integration_time: int=2000000):
        self.od = OceanDirectAPI()
        self.device_id = None
        self.is_connected = False
        self.integration_time = integration_time

    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def detect(self):
        device_count = self.od.find_devices()
        return device_count > 0

    def connect(self):

        if not self.detect():
            raise RuntimeError("No spectrometer devices found")
        
        device_ids = self.od.get_device_ids()

        if not device_ids:
            raise RuntimeError("Device IDs not available")

        self.device_id = device_ids[0] 
        self.od.open_device(self.device_id)

        self.is_connected = True

    def acquire_spectrum(self):
        if not self.is_connected:
            raise Exception("Spectrometer not connected")

        self.od.set_integration_time(self.integration_time)
        wavelengths = self.od.get_wavelengths()
        spectrum = self.od.get_formatted_spectrum()

        out_file = export_spectrum_to_csv( wavelengths, spectrum)

        return out_file

    def close(self):
        if self.is_connected:
            self.od.close_device(self.device_id)
            self.is_connected = False


def export_spectrum_to_csv(wavelengths, intensities):
    x = list(wavelengths)
    y = list(intensities)
    n = min(len(x), len(y))
    
    out_file = os.path.join(RAW_DIR, f"spectrum_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    with open(out_file, 'w', newline="") as csvfile:
        writer = csv.writer(csvfile)

        for i in range(n):
            writer.writerow([x[i], y[i]])
    return out_file