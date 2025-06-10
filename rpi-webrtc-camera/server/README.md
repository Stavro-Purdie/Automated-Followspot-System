# Raspberry Pi WebRTC Camera Server

This project sets up a WebRTC server using a Raspberry Pi connected to a Pi Camera 3 NOIR. The server streams video and allows remote focus control from a client application. Additionally, it processes infrared (IR) beacon signals to create a HOT/COLD view, where hot areas are displayed in white and cold areas in black.

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
- [File Structure](#file-structure)
- [Dependencies](#dependencies)

## Installation

1. **Clone the repository:**
   ```
   git clone <repository-url>
   cd rpi-webrtc-camera
   ```

2. **Install the required Python packages:**
   Navigate to the `server` directory and install the dependencies listed in `requirements.txt`:
   ```
   cd server
   pip install -r requirements.txt
   ```

3. **Set up the Pi Camera:**
   Ensure that the Pi Camera is enabled in the Raspberry Pi configuration settings.

## Usage

1. **Start the WebRTC server:**
   Run the server script from the `server` directory:
   ```
   python server.py
   ```

2. **Access the client application:**
   Open a web browser and navigate to the client application hosted on the Raspberry Pi. The default address is:
   ```
   http://<raspberry-pi-ip>:<port>
   ```

3. **Control the camera:**
   Use the client interface to connect to the server, view the video stream, and adjust the focus.

4. **View HOT/COLD representation:**
   The server processes the camera feed to display temperature variations based on IR beacon signals.

## File Structure

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
│   │   ├── client.js       # JavaScript for client functionality
│   │   └── webrtc.js       # WebRTC-specific JavaScript code
│   ├── css
│   │   └── style.css       # CSS styles for the client application
│   └── README.md           # Documentation for the client application
├── static
│   └── icons
│       └── favicon.ico     # Favicon for the client application
├── .gitignore              # Files and directories to ignore by Git
└── README.md               # Overview of the entire project
```

## Dependencies

- `aiortc`: For WebRTC signaling and media streaming.
- `opencv-python`: For image processing and camera control.
- `picamera`: For interfacing with the Raspberry Pi camera.
- `numpy`: For numerical operations and image manipulation.

Ensure all dependencies are installed before running the server.