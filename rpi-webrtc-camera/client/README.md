# Raspberry Pi WebRTC Camera Client

This directory contains the client application for the Raspberry Pi WebRTC Camera project. The client connects to the WebRTC server running on the Raspberry Pi and allows users to view the video stream from the Pi Camera 3 NOIR. It also provides functionality for remote focus control and displays a HOT/COLD view based on IR beacon processing.

## Files Overview

- **index.html**: The main HTML file that sets up the user interface for the client application.
- **js/client.js**: JavaScript code that manages the connection to the WebRTC server, handles video streaming, and implements focus control.
- **js/webrtc.js**: JavaScript code specific to WebRTC functionality, managing peer connections, SDP offers, answers, and ICE candidates.
- **css/style.css**: CSS styles that define the layout and appearance of the client application.

## Usage Instructions

1. **Setup**: Ensure that the server is running on the Raspberry Pi. Follow the instructions in the `server/README.md` file to set up and start the server.

2. **Connect to the Server**: Open the `index.html` file in a web browser. Enter the server's IP address and port to connect.

3. **View Video Stream**: Once connected, the video stream from the Pi Camera will be displayed in the browser.

4. **Focus Control**: Use the provided controls to adjust the camera's focus remotely.

5. **HOT/COLD View**: The application will process IR beacon signals to display a HOT/COLD view, where white represents hot areas and black represents cold areas.

## Requirements

- A modern web browser that supports WebRTC.
- Ensure that the Raspberry Pi and the client device are on the same network for seamless connectivity.

## Troubleshooting

- If you encounter issues connecting to the server, verify the server's IP address and port.
- Check the console for any JavaScript errors that may indicate problems with the WebRTC connection.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.