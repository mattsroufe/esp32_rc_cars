# ESP32 RC Cars

![](car_photo.jpeg)

![](screenshot.png)

## Demo video

https://youtu.be/OubYFXmvA1E

This project demonstrates an ESP32-based remote-controlled camera system capable of transmitting live video streams over WebSockets and controlling motors and servos. A Python server application manages WebSocket communication and provides a web interface to view and control the ESP32 devices.

## Features

- Live video streaming from an ESP32-CAM to a web server.
- Remote control of a motor and a servo via WebSocket commands.
- Automatic timeout to reset motor and servo to default states.
- Dynamic multi-client video feed canvas on the server.

---

## Hardware Requirements

- ESP32-CAM (AI Thinker module or compatible board).
- Motor and servo connected to appropriate GPIO pins.
- Stable 5V power supply for the ESP32-CAM.
- Optional SD card (if required for other functionalities).
- Wi-Fi network for communication.

---

## Software Requirements

### ESP32 Code

#### Libraries

- `WiFi.h` for Wi-Fi connectivity.
- `ArduinoWebsockets.h` for WebSocket communication.
- `esp_camera.h` for ESP32-CAM camera control.
- `ServoControl.h` and `Esc.h` for controlling the servo and motor.
- `Arduino.h` for standard Arduino functions.

### Python Server

#### Dependencies

Install the following Python libraries:

```bash
pip3 install aiohttp opencv-python numpy
```

---

## Configuration

### ESP32 Firmware

1. Modify the `secrets.h` file to include your Wi-Fi credentials and WebSocket server URL:

```cpp
#define WIFI_SSID "YourWiFiSSID"
#define WIFI_PASSWORD "YourWiFiPassword"
#define WS_SERVER_URL "ws://YourServerIP:Port"
```

2. Ensure the GPIO pins for the camera module, motor, and servo match your hardware setup:

- Camera GPIO pins are pre-configured for the AI Thinker ESP32-CAM board.
- Update motor and servo pins if necessary.

### Python Server

1. Place the server script in a directory with an `index.html` file for the web interface.
2. Start the server:

```bash
python3 server.py
```

The server will be accessible on `http://localhost:8080/`.

---

## Usage

### ESP32

1. Upload the provided sketch to your ESP32-CAM using the Arduino IDE or a compatible platform.
2. Monitor the serial output to ensure successful connection to Wi-Fi and the WebSocket server.

### Server

1. Run the Python server script.
2. Open the web interface in a browser to view the live video streams.
3. Send control commands via the WebSocket connection.

### WebSocket Commands

- `MOTOR:<speed>`: Set motor speed (-255 to 255).
- `SERVO:<angle>`: Set servo angle (0 to 180).
- `CONTROL:<speed>:<angle>`: Control both motor speed and servo angle simultaneously.

---

## Technical Details

### ESP32 Initialization

- **Wi-Fi**: Connects to the specified Wi-Fi network.
- **Camera**: Configures the ESP32-CAM with the appropriate settings for video streaming.
- **WebSocket**: Establishes a WebSocket connection with the server.

### Timeout Handling

If no control commands are received within a predefined timeout period, the motor speed resets to `0`, and the servo angle resets to `90`.

### Python Server

- Handles WebSocket communication with multiple ESP32 clients.
- Processes incoming video frames and dynamically arranges them in a grid.
- Streams the grid of video frames to the web interface.

---

## Troubleshooting

- **Connection Issues**:
  - Verify Wi-Fi credentials in `secrets.h`.
  - Check that the WebSocket server is running and accessible.

- **Video Stream Issues**:
  - Ensure proper power supply to the ESP32-CAM.
  - Verify camera initialization settings.

---

## License

This project is open-source and available under the MIT License.

---

## Contribution

Feel free to submit issues or pull requests to improve the application!
