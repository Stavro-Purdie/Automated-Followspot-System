# Raspberry Pi WebRTC Camera Project

This project enables real-time video streaming from a Raspberry Pi equipped with a Pi Camera 3 NOIR. It utilizes WebRTC for low-latency communication and allows remote focus control. Additionally, it processes infrared (IR) signals to create a HOT/COLD view, where hot areas are displayed in white and cold areas in black.

## Project Structure

```
rpi-webrtc-camera
├── server
│   ├── server.py          # Main entry point for the WebRTC server
│   ├── ir_processor.py     # Logic for processing IR beacon signals
│   ├── requirements.txt    # Python dependencies for the server
│   └── README.md           # Documentation for the server
├── client
│   ├── index.html          # Main HTML file for the client application
│   ├── js
│   │   ├── client.js       # JavaScript for client application functionality
│   │   └── webrtc.js       # WebRTC-specific JavaScript code
│   ├── css
│   │   └── style.css       # CSS styles for the client application
│   └── README.md           # Documentation for the client application
├── static
│   └── icons
│       └── favicon.ico      # Favicon for the client application
├── .gitignore               # Git ignore file
└── README.md                # Overview of the entire project
```

## Features

- **Real-time Video Streaming**: Stream video from the Raspberry Pi Camera 3 NOIR using WebRTC.
- **Remote Focus Control**: Adjust the camera focus remotely through the client interface.
- **IR Beacon Processing**: Analyze the camera feed to create a HOT/COLD view based on IR signals.

## Installation

1. **Clone the repository**:
   ```
   git clone https://github.com/yourusername/rpi-webrtc-camera.git
   cd rpi-webrtc-camera
   ```

2. **Install server dependencies**:
   Navigate to the `server` directory and install the required Python packages:
   ```
   cd server
   pip install -r requirements.txt
   ```

3. **Run the server**:
   Execute the server script:
   ```
   python server.py
   ```

4. **Access the client**:
   Open `client/index.html` in a web browser to connect to the WebRTC server and view the video stream.

## Usage

- Use the client interface to connect to the Raspberry Pi server.
- Adjust the focus using the provided controls.
- Observe the HOT/COLD view generated from the IR signals detected by the camera.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.