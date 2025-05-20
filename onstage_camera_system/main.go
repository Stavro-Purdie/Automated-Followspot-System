// Main Program for the On-Stage Camera Package
// It is licensed under the MIT License.
// Stavro Purdie '25
package main

import (
	"context"
	"flag"
	"io"
	"log"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	// Parse command line flags into config
	config := NewDefaultConfig()
	flag.StringVar(&config.DevicePath, "device", config.DevicePath, "Path to the camera device")
	flag.IntVar(&config.Width, "width", config.Width, "Width of the camera stream")
	flag.IntVar(&config.Height, "height", config.Height, "Height of the camera stream")
	flag.IntVar(&config.FPS, "fps", config.FPS, "Frames per second")
	flag.StringVar(&config.PixelFormat, "pixel-format", config.PixelFormat, "Pixel format of the camera stream")
	flag.BoolVar(&config.IRMode, "ir-mode", config.IRMode, "Enable IR mode")
	flag.IntVar(&config.RTSPPort, "rtsp-port", config.RTSPPort, "RTSP port to stream on")
	flag.StringVar(&config.StreamPath, "stream-path", config.StreamPath, "RTSP stream path")
	flag.BoolVar(&config.Verbose, "verbose", config.Verbose, "Enable verbose logging")
	flag.Parse()

	// Set up logger
	logger := log.New(os.Stdout, "", log.LstdFlags)
	if !config.Verbose {
		logger.SetOutput(io.Discard) // Disable logging if not verbose
	}

	// Create context with cancellation for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Handle OS signals for graceful shutdown
	signalChan := make(chan os.Signal, 1)
	signal.Notify(signalChan, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		signal := <-signalChan
		logger.Printf("Received signal: %s, shutting down...", signal)
		cancel()
	}()

	// Initialize camera
	camera, err := NewCamera(ctx, config, logger)
	if err != nil {
		logger.Fatalf("Failed to initialize camera: %v", err)
	}
	defer camera.Close()

	// Start RTSP Server
	server, err := NewRTSPServer(camera, config, logger)
	if err != nil {
		logger.Fatalf("Failed to start RTSP server: %v", err)
	}
	defer server.Close()

	// Print connection info
	logger.Printf("RTSP server started at rtsp://localhost:%d%s", config.RTSPPort, config.StreamPath)

	// Main loop -- Wait for context to be cancelled
	<-ctx.Done()
	logger.Println("Shutting down...")
}
