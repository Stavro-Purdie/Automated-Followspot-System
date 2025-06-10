const videoElement = document.getElementById('video');
const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');
const focusSlider = document.getElementById('focusSlider');
const focusValueLabel = document.getElementById('focusValue');
const signalingServerUrl = 'ws://your_signaling_server_url'; // Replace with your signaling server URL
let localStream;
let peerConnection;
const iceServers = {
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' }
    ]
};

startButton.onclick = startStreaming;
stopButton.onclick = stopStreaming;
focusSlider.oninput = updateFocus;

function startStreaming() {
    navigator.mediaDevices.getUserMedia({ video: true })
        .then(stream => {
            localStream = stream;
            videoElement.srcObject = stream;
            initializeWebRTC();
        })
        .catch(error => {
            console.error('Error accessing media devices.', error);
        });
}

function stopStreaming() {
    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
        videoElement.srcObject = null;
    }
    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }
}

function initializeWebRTC() {
    peerConnection = new RTCPeerConnection(iceServers);
    localStream.getTracks().forEach(track => peerConnection.addTrack(track, localStream));

    peerConnection.onicecandidate = event => {
        if (event.candidate) {
            sendMessage({ type: 'icecandidate', candidate: event.candidate });
        }
    };

    peerConnection.ontrack = event => {
        const remoteVideo = document.getElementById('remoteVideo');
        remoteVideo.srcObject = event.streams[0];
    };

    // Connect to signaling server
    const signalingSocket = new WebSocket(signalingServerUrl);
    signalingSocket.onmessage = handleSignalingMessage;

    signalingSocket.onopen = () => {
        createOffer();
    };
}

function createOffer() {
    peerConnection.createOffer()
        .then(offer => {
            return peerConnection.setLocalDescription(offer);
        })
        .then(() => {
            sendMessage({ type: 'offer', sdp: peerConnection.localDescription });
        })
        .catch(error => {
            console.error('Error creating offer:', error);
        });
}

function handleSignalingMessage(message) {
    const data = JSON.parse(message.data);
    switch (data.type) {
        case 'answer':
            peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));
            break;
        case 'icecandidate':
            peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
            break;
    }
}

function sendMessage(message) {
    // Implement sending message to signaling server
}

function updateFocus() {
    const focusValue = focusSlider.value;
    focusValueLabel.textContent = focusValue;
    // Send focus value to server
    sendMessage({ type: 'focus', value: focusValue });
}