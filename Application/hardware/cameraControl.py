from harvesters.core import Harvester
import time

class Camera:
    def __init__(self, cti_path="/opt/cvb-15.00.003/drivers/genicam/libCVUSBTL.cti"):
        self.cti_path = cti_path
        self.h = None
        self.ia = None

    def init(self):
        self.h = Harvester()
        self.h.add_file(self.cti_path)
        self.h.update()

        print(f"Found {len(self.h.device_info_list)} device(s):\n")
        for i, device_info in enumerate(self.h.device_info_list):
            print(f"Device {i}:")
            print(f"  Model:         {device_info.model}")
            print(f"  Serial:        {device_info.serial_number}")
            print(f"  Vendor:        {device_info.vendor}")
            print(f"  Access Status: {device_info.access_status}")
            print(f"  Is Available:  {device_info.access_status == 1}")
            print()

        self.ia = self.h.create(0)
        time.sleep(1)
        return True

    def read_image_info(self):
        nm = self.ia.remote_device.node_map
        print(f"Width:  {nm.Width.value}")
        print(f"Height: {nm.Height.value}")
        print(f"Format: {nm.PixelFormat.value}")

    def get_test_image(self):
        print("Fetching a test image...")
        self.ia.start()

        with self.ia.fetch() as buffer:
            component = buffer.payload.components[0]
            print(f"  Image Width:  {component.width}")
            print(f"  Image Height: {component.height}")
            print(f"  Pixel Format: {component.data_format}")
            print("  Image fetch successful!")

        self.ia.stop()

    def close(self):
        if self.ia:
            self.ia.destroy()
            self.ia = None
        if self.h:
            self.h.reset()
            self.h = None

    # Allows use of `with Camera() as cam:`
    def __enter__(self):
        self.init()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()