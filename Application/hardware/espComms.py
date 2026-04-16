import serial

class espComms:

    def __init__(self, port, baudrate=115200, timeout=2):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        try:
            self.ser = serial.Serial(port, baudrate, timeout=timeout)
            print(f"Connected to ESP32 on {port}")
        except Exception as e:
            print(f"Failed to open serial port: {e}")
            self.ser = None

    def send_servo_command(self, value):
        """Send command '1' to ESP32 to initiate servo movement"""
        if not self.ser:
            print("Serial connection not available")
            return

        try:
            command = f"{value}\r\n".encode('utf-8')
            self.ser.write(command)
            print("Command sent to ESP32")

            response = self.ser.readline().decode('utf-8').strip()

            if response:
                print(f"ESP32 response: {response}")
            else:
                print("No response received from ESP32")

        except Exception as e:
            print(f"Error in communication: {e}")

    def close(self):
        """Close serial connection"""
        if self.ser:
            self.ser.close()
            print("Serial connection closed")