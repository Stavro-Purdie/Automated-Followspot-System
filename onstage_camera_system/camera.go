//Camera side driving software for the On-Stage Camera System

package main

import (
	"context"
	"fmt"
	"log"

	"github.com/vladimirvivien/go4vl/device"
	"github.com/vladimirvivien/go4vl/v4l2"
)

// Camera represents the video capture device
type Camera struct {
	device *device.Device
	config *Config
	logger *log.Logger
}

// NewCamera initializes a new camera instance with the given configuration
func NewCamera(ctx context.Context, config *Config, logger *log.Logger) (*Camera, error) {
	logger.Println("Initializing camera...")

	// Buffer size calculation
	bufSize := (config.Width * config.Height * 2) // Very Conservative Estimate for Raspberry Pi

	//Open V4L2 Device
	dev, err := device.Open(config.DevicePath,
		device.WithIOType(v4l2.IOTypeMMAP),
		device.WithPixFormat(v4l2.PixFormat{
			PixelFormat: getPixelFormat(config.PixelFormat),
			Width:       uint32(config.Width),
			Height:      uint32(config.Height),
			Field:       v4l2.FieldNone,
		}),
		device.WithBufferSize(uint32(bufSize)),
		device.WithFPS(uint32(config.FPS)),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to open camera device: %w", err)
	}

	camera := &Camera{
		device: dev,
		config: config,
		logger: logger,
	}

	// Configure IR Mode if enabled
	if config.IRMode {
		if err := camera.configureIRMode(); err != nil {
			return nil, fmt.Errorf("failed to configure IR mode: %w", err)
		}
	}

	//Start Streaming
	if err := dev.Start(ctx); err != nil {
		dev.Close()
		return nil, fmt.Errorf("failed to start streaming: %w", err)
	}

	logger.Printf("Camera initialized: %dx%d@%d FPS", config.Width, config.Height, config.FPS)
	return camera, nil
}

// Release Camera Resources When Shutdown
func (c *Camera) Close() error {
	return c.device.Close()
}

// getrFrame returns a video frame from the camera
func (c *Camera) GetFrame() (*device.Frame, error) {
	return c.device.GetFrame()
}

// configureIRMode sets up the camera for infrared video
func (c *Camera) configureIRMode() error {
	c.logger.Println("Enabling IR mode...")

	// These are common controls, but they vary by device
	controls := []struct {
		id    uint32
		value int32
	}{
		{v4l2.CtrlAutoWhiteBalance, 0},   // Disable auto white balance
		{v4l2.CtrlExposureAuto, 1},       // Set auto exposure to manual
		{v4l2.CtrlExposureAbsolute, 500}, // Set exposure value
		{v4l2.CtrlGain, 50},              // Set gain
		{0x009a0903, 1},                  // Custom control ID for IR cut filter (example)
	}

	for _, ctrl := range controls {
		// Ignore errors as not all cameras support all controls
		_ = c.device.SetControlValue(ctrl.id, ctrl.value)
	}

	return nil
}

// getPixelFormat converts string format to V4L2 pixel format
func getPixelFormat(format string) uint32 {
	switch format {
	case "H264":
		return v4l2.PixelFmtH264
	case "MJPEG":
		return v4l2.PixelFmtMJPEG
	case "YUYV":
		return v4l2.PixelFmtYUYV
	default:
		log.Printf("Unknown format %s, using H264", format)
		return v4l2.PixelFmtH264
	}
}
