const signalingServerUrl = 'ws://localhost:8080'; // Change to your server URL
let localStream;
let peerConnection;
const iceServers = {
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' } // STUN server for NAT traversal
    ]
};

async function startStream() {
    const constraints = {
        video: { facingMode: 'user' }, // Use the front camera
        audio: false
    };

    try {
        localStream = await navigator.mediaDevices.getUserMedia(constraints);
        document.getElementById('localVideo').srcObject = localStream;
    } catch (error) {
        console.error('Error accessing media devices.', error);
    }
}

function createPeerConnection() {
    peerConnection = new RTCPeerConnection(iceServers);

    localStream.getTracks().forEach(track => {
        peerConnection.addTrack(track, localStream);
    });

    peerConnection.onicecandidate = event => {
        if (event.candidate) {
            sendMessage({ type: 'candidate', candidate: event.candidate });
        }
    };

    peerConnection.ontrack = event => {
        const remoteVideo = document.getElementById('remoteVideo');
        remoteVideo.srcObject = event.streams[0];
    };
}

async function handleOffer(offer) {
    await peerConnection.setRemoteDescription(new RTCSessionDescription(offer));
    const answer = await peerConnection.createAnswer();
    await peerConnection.setLocalDescription(answer);
    sendMessage({ type: 'answer', sdp: answer.sdp });
}

function sendMessage(message) {
    const socket = new WebSocket(signalingServerUrl);
    socket.onopen = () => {
        socket.send(JSON.stringify(message));
    };
}

document.getElementById('startButton').onclick = async () => {
    await startStream();
    createPeerConnection();
    sendMessage({ type: 'start' });
};

document.getElementById('focusControl').oninput = function() {
    const focusValue = this.value;
    sendMessage({ type: 'focus', value: focusValue });
};