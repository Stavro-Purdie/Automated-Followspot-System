package main

import (
	"fmt"
	"log"
	"strconv"
	"time"

	"github.com/aler9/gortsplib/v2"
	"github.com/aler9/gortsplib/v2/pkg/formats"
	"github.com/aler9/gortsplib/v2/pkg/formats/rtph264"
	"github.com/aler9/gortsplib/v2/pkg/media"
	"github.com/pion/rtp"
)

// RTSPServer handles the RTSP streaming
type RTSPServer struct {
	server  *gortsplib.Server
	camera  *Camera
	config  *Config
	logger  *log.Logger
	handler *RTSPHandler
}

// New RTSPServer Creates a new RTSP server
func NewRTSPServer(camera *Camera, config *Config, logger *log.Logger) (*RTSPServer, error) {
	logger.Println("Initializing RTSP server...")

	// Create Handler
	handler := &RTSPHandler{
		camera:     camera,
		logger:     logger,
		config:     config,
		streamPath: config.StreamPath,
	}

	// Initialize Server
	server := &gortsplib.Server{
		Handler:     handler,
		RTSPAddress: ":" + strconv.Itoa(config.RTSPPort),
	}

	// Create Server Instance
	rtspServer := &RTSPServer{
		server:  server,
		camera:  camera,
		config:  config,
		logger:  logger,
		handler: handler,
	}

	// Start RTSP Server
	if err := rtspServer.server.Start(); err != nil {
		return nil, fmt.Errorf("failed to start RTSP server: %w", err)
	}
	logger.Printf("RTSP server running on rtsp://0.0.0.0:%d/%s", config.RTSPPort, config.StreamPath)
	return rtspServer, nil
}

// Close stops the RTSP Server
func (s *RTSPServer) Close() error {
	s.server.Close()
	return nil
}

// RTSPHandler implements the gortsplib.ServerHandler interface
type RTSPHandler struct {
	camera     *Camera
	logger     *log.Logger
	config     *Config
	streamPath string

	// RTSP session state
	medias     []*media.Media
	streams    []*rtspStream
	videoTrack *formats.H264
}

type rtspStream struct {
	udpRTPListener  *gortsplib.UDPListener
	udpRTCPListener *gortsplib.UDPListener
	rtcpReciever    *rtph264.RTPReceiver
}

// OnConnOpen implements gortsplib.Handler
func (h *RTSPHandler) OnConnOpen(ctx *gortsplib.ServerHandlerOnConnOpenCtx) {
	h.logger.Printf("Connection opened from %s", ctx.Conn.NetConn().RemoteAddr())
}

// OnConnClose implements gortsplib.Handler
func (h *RTSPHandler) OnConnClose(ctx *gortsplib.ServerHandlerOnConnCloseCtx) {
	h.logger.Printf("Connection closed from %s", ctx.Conn.NetConn().RemoteAddr())
}

// OnDescribe implements gortsplib.Handler
func (h *RTSPHandler) OnDescribe(ctx *gortsplib.ServerHandlerOnDescribeCtx) (*media.MediaInfo, error) {
	h.logger.Printf("Got DESCRIBE request from %s", ctx.Conn.NetConn().RemoteAddr())

	// Check Path
	if ctx.Path != h.streamPath {
		return nil, fmt.Errorf("path not found: %s", ctx.Path)
	}

	// Initialize H264 video track if needed
	if h.videoTrack == nil {
		// Create H264 track
		h.videoTrack = &formats.H264{
			PayloadTyp:        96,
			SPS:               []byte{}, // Should be populated with actual SPS from camera
			PPS:               []byte{}, // Should be populated with actual PPS from camera
			PacketizationMode: 1,
		}

		// Create media
		videoMedia := &media.Media{
			Type:    media.TypeVideo,
			Formats: []formats.Format{h.videoTrack},
		}

		h.medias = []*media.Media{videoMedia}
	}

	return &media.MediaInfo{
		Medias: h.medias,
	}, nil
}

// OnSetup implements gortsplib.Handler
func (h *RTSPHandler) OnSetup(ctx *gortsplib.ServerHandlerOnSetupCtx) (*gortsplib.ServerHandlerOnSetupRes, error) {
	h.logger.Printf("Got SETUP request from %s", ctx.Conn.NetConn().RemoteAddr())

	// Initialize streams on first setup
	if h.streams == nil {
		h.streams = make([]*rtspStream, len(h.medias))
		for i := range h.streams {
			h.streams[i] = &rtspStream{}
		}
	}

	//Get Stream
	stream := h.streams[ctx.MediaIndex]

	switch ctx.Transport.Protocol {
	case gortsplib.TransportProtocolUDP:
		// Handle UDP transport
		return &gortsplib.ServerHandlerOnSetupRes{
			Transport: &gortsplib.Transport{
				Protocol: gortsplib.TransportProtocolUDP,
				ServerPorts: &[2]int{
					ctx.Transport.ClientPorts[0],
					ctx.Transport.ClientPorts[1],
				},
				ClientPorts: ctx.Transport.ClientPorts,
			},
		}, nil

	case gortsplib.TransportProtocolTCP:
		// Handle TCP transport
		return &gortsplib.ServerHandlerOnSetupRes{
			Transport: &gortsplib.Transport{
				Protocol:       gortsplib.TransportProtocolTCP,
				InterleavedIDs: ctx.Transport.InterleavedIDs,
			},
		}, nil

	default:
		return nil, fmt.Errorf("unhandled transport protocol: %v", ctx.Transport.Protocol)
	}
}

// OnPlay implements gortsplib.Handler
func (h *RTSPHandler) OnPlay(ctx *gortsplib.ServerHandlerOnPlayCtx) (*gortsplib.ServerHandlerOnPlayRes, error) {
	h.logger.Printf("Got PLAY request from %s", ctx.Conn.NetConn().RemoteAddr())

	// Start feeding frames to the client
	go h.streamFrames(ctx.Conn)

	return &gortsplib.ServerHandlerOnPlayRes{}, nil
}

// OnPause implements gortsplib.Handler
func (h *RTSPHandler) OnPause(ctx *gortsplib.ServerHandlerOnPauseCtx) (*gortsplib.ServerHandlerOnPauseRes, error) {
	h.logger.Printf("Got PAUSE request from %s", ctx.Conn.NetConn().RemoteAddr())
	return &gortsplib.ServerHandlerOnPauseRes{}, nil
}

// streamFrames reads frames from the camera and sends them to the RTSP client
func (h *RTSPHandler) streamFrames(conn *gortsplib.ServerConn) {
	ticker := time.NewTicker(time.Second / time.Duration(h.config.FPS))
	defer ticker.Stop()

	// Setup for RTP packets
	frameCounter := uint32(0)
	timestamp := uint32(0)
	timestampInc := uint32(90000 / h.config.FPS) // RTP timestamp increment (90kHz clock)

	for range ticker.C {
		// Check if client is still connected
		if conn.State() != gortsplib.ServerConnStatePlay {
			break
		}

		// Get frame from camera
		frame, err := h.camera.GetFrame()
		if err != nil {
			h.logger.Printf("Error getting frame: %v", err)
			continue
		}

		// Create RTP packets from the frame
		pkts := rtph264.Packetize(frame.Data(), 1400)
		for i, pkt := range pkts {
			// Set markers
			pkt.Header.Timestamp = timestamp
			pkt.Header.SequenceNumber = frameCounter
			pkt.Header.Marker = (i == len(pkts)-1) // Mark last packet of frame

			// Write to client
			conn.WritePacketRTP(h.medias[0], h.videoTrack, &rtp.Packet{
				Header:  pkt.Header,
				Payload: pkt.Payload,
			})

			frameCounter++
		}

		// Release frame
		frame.Release()

		// Update timestamp for next frame
		timestamp += timestampInc
	}

	h.logger.Printf("Client %s disconnected", conn.NetConn().RemoteAddr())
}

// OnRemoveSession implements gortsplib.Handler
func (h *RTSPHandler) OnRemoveSession(ctx *gortsplib.ServerHandlerOnRemoveSessionCtx) {
	h.logger.Printf("Session from %s removed", ctx.Conn.NetConn().RemoteAddr())
}
