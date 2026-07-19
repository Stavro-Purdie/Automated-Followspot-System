#!/usr/bin/env python3
"""Unit tests for DMX transport and encoder."""

import sys
from pathlib import Path
import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from node.dmx_transport import (
    DMXFrame, DMXEncoder, StubTransport, 
    RS485Transport, ArtNetTransport, SACNTransport,
    create_transport, RS485Transport
)


class TestDMXFrame:
    """Test DMX frame structure."""
    
    def test_frame_creation(self):
        """Test DMX frame with 513 bytes (start code + 512 channels)."""
        data = bytearray(513)
        data[0] = 0  # Start code
        frame = DMXFrame(data=data, universe=1)
        assert len(frame.data) == 513
        assert frame.data[0] == 0
        assert frame.universe == 1
    
    def test_frame_invalid_length(self):
        """Test frame rejects invalid length."""
        data = bytearray(512)  # Missing start code
        with pytest.raises(ValueError):
            DMXFrame(data=data)


class TestDMXEncoder:
    """Test DMX encoder with fixture profiles."""
    
    def test_generic_moving_head_profile(self):
        """Test encoder with generic moving head profile."""
        profile = {
            "pan_coarse": 1, "pan_fine": 2,
            "tilt_coarse": 3, "tilt_fine": 4,
            "dimmer": 5,
            "pan_min_deg": -180.0, "pan_max_deg": 180.0,
            "tilt_min_deg": -90.0, "tilt_max_deg": 90.0,
            "pan_scale": 1.0, "tilt_scale": 1.0,
        }
        encoder = DMXEncoder(profile)
        
        # Test center position
        frame = encoder.encode(0.0, 0.0, 100.0)
        # 0 deg should map to 32767 (middle of 16-bit range)
        assert frame.data[1] == 127  # pan coarse
        assert frame.data[2] == 255  # pan fine
        assert frame.data[3] == 127  # tilt coarse
        assert frame.data[4] == 255  # tilt fine
        assert frame.data[5] == 255  # dimmer at 100%
    
    def test_pan_tilt_limits(self):
        """Test pan/tilt clamping to fixture limits."""
        profile = {
            "pan_coarse": 1, "pan_fine": 2,
            "tilt_coarse": 3, "tilt_fine": 4,
            "dimmer": 5,
            "pan_min_deg": -120.0, "pan_max_deg": 120.0,
            "tilt_min_deg": -120.0, "tilt_max_deg": 10.0,
        }
        encoder = DMXEncoder(profile)
        
        # Request beyond limits should clamp
        frame = encoder.encode(200.0, -200.0, 100.0)
        # Should clamp to max pan (120) and min tilt (-120)
        # 120 deg maps to 65535, -120 deg maps to 0
        pan_val = (frame.data[1] << 8) | frame.data[2]
        tilt_val = (frame.data[3] << 8) | frame.data[4]
        assert pan_val == 65535  # Max
        assert tilt_val == 0     # Min
    
    def test_brightness_scaling(self):
        """Test dimmer channel scales with brightness."""
        profile = {"pan_coarse": 1, "pan_fine": 2, "tilt_coarse": 3, "tilt_fine": 4, "dimmer": 5}
        encoder = DMXEncoder(profile)
        
        frame = encoder.encode(0.0, 0.0, 50.0)
        # 50% of 255 = 127.5 -> truncated to 127
        assert frame.data[5] == 127
        
        frame = encoder.encode(0.0, 0.0, 0.0)
        assert frame.data[5] == 0
        
        frame = encoder.encode(0.0, 0.0, 100.0)
        assert frame.data[5] == 255
    
    def test_scale_factors(self):
        """Test pan/tilt scale factors."""
        profile = {
            "pan_coarse": 1, "pan_fine": 2,
            "tilt_coarse": 3, "tilt_fine": 4,
            "dimmer": 5,
            "pan_scale": 0.5, "tilt_scale": 2.0,
        }
        encoder = DMXEncoder(profile)
        
        frame = encoder.encode(180.0, 90.0, 100.0)
        # With pan_scale=0.5, 180 should map to half range
        # With tilt_scale=2.0, 90 should map to full range (clamped)
        pan_val = (frame.data[1] << 8) | frame.data[2]
        tilt_val = (frame.data[3] << 8) | frame.data[4]
        assert pan_val == 32767  # Half range
        assert tilt_val == 65535  # Full range (clamped)


class TestStubTransport:
    """Test stub transport for testing."""
    
    def test_send_frame(self):
        """Test stub transport accepts frames."""
        transport = StubTransport()
        assert transport.is_ready
        
        frame = DMXFrame(data=bytearray(513), universe=1)
        result = transport.send(frame)
        assert result is True
        assert transport.last_frame is not None


class TestTransportFactory:
    """Test transport factory function."""
    
    def test_create_stub(self):
        """Test creating stub transport."""
        config = {"transport": "stub", "universe": 1}
        transport = create_transport(config)
        assert isinstance(transport, StubTransport)
    
    def test_create_rs485(self):
        """Test creating RS485 transport."""
        config = {"transport": "rs485_serial", "serial_port": "/dev/ttyAMA0", "universe": 1}
        transport = create_transport(config)
        assert isinstance(transport, RS485Transport)
    
    def test_create_artnet(self):
        """Test creating Art-Net transport."""
        config = {"transport": "artnet", "artnet_ip": "2.0.0.1", "universe": 1}
        transport = create_transport(config)
        assert isinstance(transport, ArtNetTransport)
    
    def test_create_sacn(self):
        """Test creating sACN transport."""
        config = {"transport": "sacn", "universe": 1}
        transport = create_transport(config)
        assert isinstance(transport, SACNTransport)


class TestFixtureProfiles:
    """Test fixture profile loading."""
    
    def test_generic_profile_structure(self):
        """Test generic moving head profile has required fields."""
        import json
        with open(PROJECT_ROOT / "config/fixture_profiles.json") as f:
            data = json.load(f)
        
        profile = data["fixture_profiles"]["generic_moving_head"]
        assert profile["pan_coarse"] == 1
        assert profile["pan_fine"] == 2
        assert profile["tilt_coarse"] == 3
        assert profile["tilt_fine"] == 4
        assert profile["dimmer"] == 5
        assert "pan_min_deg" in profile
        assert "pan_max_deg" in profile


if __name__ == "__main__":
    pytest.main([__file__, "-v"])