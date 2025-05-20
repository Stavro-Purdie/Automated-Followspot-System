// This file is part of the On-Stage Camera Software Package.
// Deals with configurations and settings for the camera software.
// It is licensed under the MIT License.
// Stavro Purdie '25
package main

type Config struct {
	// Camera settings
	DevicePath  string
	Width       int
	Height      int
	FPS         int
	PixelFormat string
	IRMode      bool

	// RTSP Settings
	RTSPPort   int
	StreamPath string

	// General settings
	Verbose bool
}

// NewDefaultConfig returns a config with sensible defaults
func NewDefaultConfig() *Config {
	return &Config{
		DevicePath:  "/dev/video0",
		Width:       640,
		Height:      480,
		FPS:         30,
		PixelFormat: "H264",
		IRMode:      false,
		RTSPPort:    8554,
		StreamPath:  "stream",
		Verbose:     false,
	}
}
