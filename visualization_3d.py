#!/usr/bin/env python3
"""3D Visualization Module for Automated Followspot System.

Provides 3D visualization of:
- Stage with tracked performers
- Spotlight position, orientation, and beam
- Camera positions and fields of view
- Real-time updates from DataFusion output
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    from mpl_toolkits.mplot3d import Axes3D
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    import pyqtgraph as pg
    from pyqtgraph.opengl import GLViewWidget, GLScatterPlotItem, GLLinePlotItem, GLMeshItem
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("visualization_3d")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


@dataclass
class StageGeometry:
    """Simple stage geometry configuration."""
    width: float
    depth: float
    height: float
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)


class Stage3D:
        
    def get_floor_corners(self) -> np.ndarray:
        """Get floor corners in stage coordinates (clockwise from front-left)."""
        w, d = self.width / 2, self.depth / 2
        return np.array([
            [-w, -d, 0],  # front-left
            [w, -d, 0],   # front-right
            [w, d, 0],    # back-right
            [-w, d, 0],   # back-left
        ])
    
    def get_floor_center(self) -> np.ndarray:
        """Get stage center point."""
        return self.origin
    
    def get_walls(self) -> List[np.ndarray]:
        """Get wall segments for rendering."""
        w, d, h = self.width / 2, self.depth / 2, self.height
        # Return wall segments as [start, end] pairs
        corners = self.get_floor_corners()
        walls = []
        for i in range(4):
            p1 = corners[i]
            p2 = corners[(i + 1) % 4]
            # Bottom edge
            walls.append((p1, p2))
            # Top edge
            walls.append((p1 + [0, 0, h], p2 + [0, 0, h]))
            # Vertical edges
            walls.append((p1, p1 + [0, 0, h]))
        return walls


class Spotlight3D:
    """3D spotlight representation with beam visualization."""
    
    def __init__(self, fixture_position: np.ndarray, stage_origin: np.ndarray):
        self.fixture_position = np.array(fixture_position, dtype=float)
        self.stage_origin = np.array(stage_origin, dtype=float)
        self.pan = 0.0
        self.tilt = 0.0
        self.beam_width = 5.0  # degrees
        self.beam_length = 20.0  # meters
        
    def update_angles(self, pan: float, tilt: float):
        """Update pan/tilt angles in degrees."""
        self.pan = pan
        self.tilt = tilt
        
    def get_beam_direction(self) -> np.ndarray:
        """Get beam direction vector in world coordinates."""
        pan_rad = math.radians(self.pan)
        tilt_rad = math.radians(self.tilt)
        
        # Pan: rotation around Z (Y axis in our convention)
        # Tilt: rotation around X
        dx = math.sin(pan_rad) * math.cos(tilt_rad)
        dy = math.cos(pan_rad) * math.cos(tilt_rad)
        dz = -math.sin(tilt_rad)  # Negative because tilt down is positive
        
        return np.array([dx, dy, dz])
    
    def get_beam_cone(self, length: Optional[float] = None) -> Tuple[np.ndarray, np.ndarray]:
        """Get beam cone vertices and edges for rendering.
        
        Returns:
            vertices: Nx3 array of cone vertices
            edges: List of (start_idx, end_idx) edge pairs
        """
        if length is None:
            length = self.beam_length
            
        direction = self.get_beam_direction()
        origin = self.fixture_position
        
        # Cone tip
        tip = origin + direction * length
        
        # Cone base radius
        radius = length * math.tan(math.radians(self.beam_width / 2))
        
        # Create base circle perpendicular to direction
        # Find two perpendicular vectors to direction
        if abs(direction[2]) < 0.9:
            perp1 = np.array([-direction[1], direction[0], 0])
        else:
            perp1 = np.array([direction[2], 0, -direction[0]])
        perp1 = perp1 / np.linalg.norm(perp1) * radius
        perp2 = np.cross(direction, perp1)
        perp2 = perp2 / np.linalg.norm(perp2) * radius
        
        # Create cone vertices
        num_segments = 16
        vertices = [self.fixture_position]
        
        for i in range(num_segments):
            angle = 2 * math.pi * i / num_segments
            point = self.fixture_position + perp1 * math.cos(angle) + perp2 * math.sin(angle)
            # Project to base of cone
            point = self.fixture_position + (point - self.fixture_position) * (self.beam_length / np.linalg.norm(self.fixture_position - (self.fixture_position + perp1)))
            # Simpler: just use base of cone
            base_center = self.fixture_position + self.get_beam_direction() * self.beam_length
            point = base_center + perp1 * math.cos(angle) + perp2 * math.sin(angle)
            vertices.append(point)
        
        vertices = np.array(vertices)
        
        # Create edges (lines from apex to base, and base circle)
        edges = []
        for i in range(1, len(vertices)):
            edges.append((0, i))
            next_idx = i + 1 if i < len(vertices) - 1 else 1
            edges.append((i, next_idx))
        
        return np.array(vertices), edges


class Camera3D:
    """3D camera representation with frustum visualization."""
    
    def __init__(self, camera_id: str, position: np.ndarray, rotation: np.ndarray, 
                 fov: float, aspect_ratio: float = 16/9, far_plane: float = 30.0):
        self.camera_id = camera_id
        self.position = np.array(position, dtype=float)
        self.rotation = np.array(rotation, dtype=float)
        self.fov = fov
        self.aspect_ratio = aspect_ratio
        self.far_plane = far_plane
        
    def get_frustum_corners(self) -> np.ndarray:
        """Get frustum corner points in world coordinates."""
        # Near and far plane dimensions
        near = 0.1
        far = self.far_plane
        
        # Half angles
        fov_y = math.radians(self.fov)
        fov_x = 2 * math.atan(math.tan(fov_y / 2) * self.aspect_ratio)
        
        half_height_near = near * math.tan(fov_y / 2)
        half_width_near = near * math.tan(fov_x / 2)
        half_height_far = far * math.tan(fov_y / 2)
        half_width_far = far * math.tan(fov_x / 2)
        
        # Local frustum corners (camera space, looking down -Z)
        local_corners = np.array([
            # Near plane
            [-half_width_near, -half_height_near, -near],
            [half_width_near, -half_height_near, -near],
            [half_width_near, half_height_near, -near],
            [-half_width_near, half_height_near, -near],
            # Far plane
            [-half_width_far, -half_height_far, -far],
            [half_width_far, -half_height_far, -far],
            [half_width_far, half_height_far, -far],
            [-half_width_far, half_height_far, -far],
        ])
        
        # Transform to world space (simplified - just apply position offset)
        # For full transform, we'd need rotation matrix
        world_corners = local_corners + self.position
        
        return world_corners


class Person3D:
    """3D person representation for visualization."""
    
    def __init__(self, person_id: int, position: np.ndarray, 
                 confidence: float = 1.0, color: Optional[Tuple[float, float, float]] = None):
        self.person_id = person_id
        self.position = np.array(position, dtype=float)
        self.confidence = confidence
        self.color = color or self._get_color(person_id)
        self.velocity = np.zeros(3)
        self.last_update = time.time()
        self.trail: List[np.ndarray] = []
        self.max_trail = 30
        
    @staticmethod
    def _get_color(person_id: int) -> Tuple[float, float, float]:
        """Generate consistent color for person ID."""
        np.random.seed(person_id)
        color = np.random.rand(3)
        # Ensure bright colors
        color = 0.5 + color * 0.5
        return tuple(color)
    
    def update(self, position: np.ndarray, timestamp: float):
        """Update position and velocity."""
        dt = timestamp - self.last_update
        if dt > 0:
            self.velocity = (np.array(position) - self.position) / dt
        self.position = np.array(position)
        self.last_update = timestamp
        
        # Update trail
        self.trail.append(self.position.copy())
        if len(self.trail) > self.max_trail:
            self.trail.pop(0)


class Visualization3D:
    """Main 3D visualization class using matplotlib or pyqtgraph."""
    
    def __init__(self, stage_geometry: StageGeometry, 
                 backend: str = "matplotlib"):
        self.stage = Stage3D(stage_geometry)
        self.backend = backend
        self.spotlights: List[Spotlight3D] = []
        self.cameras: List[Camera3D] = []
        self.persons: Dict[int, Person3D] = {}
        self.running = False
        
        # Visualization settings
        self.show_trails = True
        self.show_camera_frustums = True
        self.show_spotlight_beams = True
        self.show_stage_grid = True
        
        # Animation
        self.animation = None
        self.fig = None
        self.ax = None
        
    def add_spotlight(self, fixture_position: np.ndarray, 
                      stage_origin: np.ndarray) -> Spotlight3D:
        """Add a spotlight to the visualization."""
        spotlight = Spotlight3D(fixture_position, self.stage.origin)
        self.spotlights.append(spotlight)
        return spotlight
    
    def add_camera(self, camera_id: str, position: np.ndarray,
                   rotation: np.ndarray, fov: float,
                   aspect_ratio: float = 16/9, far_plane: float = 30.0) -> Camera3D:
        """Add a camera to the visualization."""
        camera = Camera3D(camera_id, position, rotation, 
                         fov=0.0, aspect_ratio=aspect_ratio, far_plane=30.0)
        self.cameras.append(camera)
        return camera
    
    def update_person(self, person_id: int, position: np.ndarray, 
                      confidence: float = 1.0, color: Optional[Tuple[float, float, float]] = None):
        """Update or create person tracking visualization."""
        if person_id not in self.persons:
            self.persons[person_id] = Person3D(person_id, position, confidence=1.0)
        self.persons[person_id].update(position, time.time())
        
    def update_spotlight(self, index: int, pan: float, tilt: float):
        """Update spotlight angles."""
        if 0 <= index < len(self.spotlights):
            self.spotlights[index].update_angles(pan, tilt)
    
    def clear_persons(self):
        """Remove all persons."""
        self.persons.clear()
    
    # --- Matplotlib Backend ---
    
    def _init_matplotlib(self):
        """Initialize matplotlib 3D plot."""
        if not MATPLOTLIB_AVAILABLE:
            raise RuntimeError("matplotlib not available")
            
        self.fig = plt.figure(figsize=(12, 10))
        self.ax = self.fig.add_subplot(111, projection='3d')
        
        # Set axis labels
        self.ax.set_xlabel('X (meters)')
        self.ax.set_ylabel('Y (meters)')
        self.ax.set_zlabel('Z (meters)')
        
        # Set equal aspect ratio
        self._set_equal_aspect()
        
        # Set initial view
        self.ax.view_init(elev=30, azim=45)
        
        # Add stage
        self._draw_stage()
        
        # Add legend
        self.ax.legend()
        
    def _set_equal_aspect(self):
        """Set equal aspect ratio for 3D plot."""
        # Get current limits
        xlim = self.ax.get_xlim3d()
        ylim = self.ax.get_ylim3d()
        zlim = self.ax.get_zlim3d()
        
        # Find the max range
        x_range = xlim[1] - xlim[0]
        y_range = ylim[1] - ylim[0]
        z_range = zlim[1] - zlim[0]
        max_range = max(x_range, y_range, z_range)
        
        # Center on stage
        x_center = (xlim[0] + xlim[1]) / 2
        y_center = (ylim[0] + ylim[1]) / 2
        z_center = (zlim[0] + zlim[1]) / 2
        
        self.ax.set_xlim3d([x_center - max_range/2, x_center + max_range/2])
        self.ax.set_ylim3d([y_center - max_range/2, y_center + max_range/2])
        self.ax.set_zlim3d([z_center - max_range/2, z_center + max_range/2])
        
    def _draw_stage(self):
        """Draw stage floor, walls, and grid."""
        if not self.show_stage_grid:
            return
            
        # Floor
        corners = self.stage.get_floor_corners()
        floor_poly = Poly3DCollection([corners], alpha=0.1, facecolor='gray', edgecolor='gray')
        self.ax.add_collection3d(floor_poly)
        
        # Floor grid
        w, d = self.stage.width / 2, self.stage.depth / 2
        for i in range(-int(self.stage.width//2), int(self.stage.width//2) + 1, 2):
            self.ax.plot([i, i], [-d, d], [0, 0], 'gray', alpha=0.3, linewidth=0.5)
        for j in range(-int(self.stage.depth//2), int(self.stage.depth//2) + 1, 2):
            self.ax.plot([-w, w], [j, j], [0, 0], 'gray', alpha=0.3, linewidth=0.5)
        
        # Origin marker
        self.ax.scatter([0], [0], [0], color='red', s=50, marker='o', label='Stage Origin')
        
        # Walls
        for p1, p2 in self.stage.get_walls():
            self.ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], 
                        'gray', alpha=0.3, linewidth=0.5)
    
    def _draw_persons(self):
        """Draw tracked persons."""
        for person in self.persons.values():
            pos = person.position
            color = person.color
            
            # Person as sphere
            u = np.linspace(0, 2 * np.pi, 20)
            v = np.linspace(0, np.pi, 10)
            radius = 0.3
            x = pos[0] + 0.3 * np.outer(np.cos(u), np.sin(v))
            y = pos[1] + 0.3 * np.outer(np.sin(u), np.sin(v))
            z = pos[2] + 0.3 * np.outer(np.ones_like(u), np.cos(v))
            
            self.ax.plot_surface(x, y, z, color=person.color, alpha=0.7, 
                               rstride=2, cstride=2, linewidth=0)
            
            # Person ID label
            self.ax.text(person.position[0], person.position[1], person.position[2] + 0.5,
                        f'P{person.person_id}', color=person.color, fontsize=8)
            
            # Velocity vector
            if np.linalg.norm(person.velocity) > 0.1:
                vel_end = person.position + person.velocity * 0.5
                self.ax.quiver(person.position[0], person.position[1], person.position[2],
                              person.velocity[0], person.velocity[1], person.velocity[2],
                              color=person.color, alpha=0.7, arrow_length_ratio=0.1)
            
            # Trail
            if self.show_trails and len(person.trail) > 1:
                trail = np.array(person.trail)
                self.ax.plot(trail[:, 0], trail[:, 1], trail[:, 2], 
                           color=person.color, alpha=0.5, linewidth=1, linestyle='--')
    
    def _draw_spotlights(self):
        """Draw spotlight beams."""
        if not self.show_spotlight_beams:
            return
            
        for i, spotlight in enumerate(self.spotlights):
            # Fixture position
            self.ax.scatter([spotlight.fixture_position[0]], 
                          [spotlight.fixture_position[1]], 
                          [spotlight.fixture_position[2]], 
                          color='yellow', s=100, marker='^', label=f'Spotlight {i+1}')
            
            # Beam cone
            vertices, edges = spotlight.get_beam_cone()
            for start_idx, end_idx in edges:
                self.ax.plot([vertices[start_idx][0], vertices[end_idx][0]],
                           [vertices[start_idx][1], vertices[end_idx][1]],
                           [vertices[start_idx][2], vertices[end_idx][2]],
                           'yellow', alpha=0.3, linewidth=0.5)
    
    def _draw_cameras(self):
        """Draw camera frustums."""
        if not self.show_camera_frustums:
            return
            
        for camera in self.cameras:
            # Camera position
            self.ax.scatter([camera.position[0]], [camera.position[1]], [camera.position[2]],
                          color='cyan', s=100, marker='s', label=f'Camera {camera.camera_id}')
            
            # Frustum
            corners = camera.get_frustum_corners()
            # Draw frustum edges
            edges = [
                (0, 1), (1, 2), (2, 3), (3, 0),  # Near plane
                (4, 5), (5, 6), (6, 7), (7, 4),  # Far plane
                (0, 4), (1, 5), (2, 6), (3, 7),  # Sides
            ]
            for i, j in edges:
                self.ax.plot([corners[i][0], corners[j][0]],
                           [corners[i][1], corners[j][1]],
                           [corners[i][2], corners[j][2]],
                           'cyan', alpha=0.3, linewidth=0.5)
    
    def _draw_spotlights(self):
        """Draw spotlight beams."""
        if not self.show_spotlight_beams:
            return
            
        for i, spotlight in enumerate(self.spotlights):
            # Fixture position
            self.ax.scatter([spotlight.fixture_position[0]], 
                          [spotlight.fixture_position[1]], 
                          [spotlight.fixture_position[2]], 
                          color='yellow', s=100, marker='^')
            
            # Beam cone
            vertices, edges = spotlight.get_beam_cone()
            for start_idx, end_idx in edges:
                self.ax.plot([vertices[start_idx][0], vertices[end_idx][0]],
                           [vertices[start_idx][1], vertices[end_idx][1]],
                           [vertices[start_idx][2], vertices[end_idx][2]],
                           'yellow', alpha=0.3, linewidth=0.5)
    
    def _update_matplotlib(self, frame):
        """Update matplotlib animation frame."""
        self.ax.clear()
        self._set_equal_aspect()
        self.ax.set_xlabel('X (meters)')
        self.ax.set_ylabel('Y (meters)')
        self.ax.set_zlabel('Z (meters)')
        self.ax.view_init(elev=30, azim=45)
        
        self._draw_stage()
        self._draw_persons()
        self._draw_spotlights()
        self._draw_cameras()
        
        self.ax.legend(loc='upper right')
        
    def run_matplotlib(self, interval: int = 100):
        """Run matplotlib animation loop."""
        if not MATPLOTLIB_AVAILABLE:
            raise RuntimeError("matplotlib not available")
            
        self._init_matplotlib()
        self.running = True
        
        self.animation = FuncAnimation(self.fig, self._update_matplotlib, 
                                      interval=interval, blit=False)
        plt.show()
    
    # --- PyQtGraph Backend (placeholder) ---
    
    def _init_pyqtgraph(self):
        """Initialize pyqtgraph 3D view."""
        if not PYQTGRAPH_AVAILABLE:
            raise RuntimeError("pyqtgraph not available")
        
        # TODO: Implement pyqtgraph backend
        raise NotImplementedError("PyQtGraph backend not yet implemented")
    
    def run_pyqtgraph(self):
        """Run pyqtgraph visualization."""
        raise NotImplementedError("PyQtGraph backend not yet implemented")


class Visualization3DServer:
    """Server for receiving real-time tracking data and updating visualization."""
    
    def __init__(self, vis: Visualization3D, host: str = '0.0.0.0', port: int = 8765):
        self.vis = vis
        self.host = host
        self.port = port
        self.running = False
        
    async def handle_client(self, reader, writer):
        """Handle incoming tracking data from client."""
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                    
                message = json.loads(data.decode())
                self._process_message(message)
                
        except Exception as e:
            logger.error(f"Client error: {e}")
        finally:
            writer.close()
            
    def _process_message(self, message: Dict[str, Any]):
        """Process incoming tracking message."""
        msg_type = message.get("type")
        
        if msg_type == "persons":
            for person in message.get("persons", []):
                self.vis.update_person(
                    person.get("id", 0),
                    np.array([person["x"], person["y"], person["z"]]),
                    person.get("confidence", 1.0)
                )
                
        elif msg_type == "spotlight":
            self.vis.update_spotlight(
                message.get("index", 0),
                message.get("pan", 0),
                message.get("tilt", 0)
            )
            
        elif msg_type == "camera":
            # Camera position update
            pass


def create_default_visualization() -> Visualization3D:
    """Create a visualization with default stage geometry."""
    from config.schemas import StageGeometry
    
    stage = StageGeometry(
        width=10.0,
        depth=8.0,
        height=3.0,
        origin=[0.0, 0.0, 0.0]
    )
    
    vis = Visualization3D(stage)
    
    # Add default spotlight (front truss)
    vis.add_spotlight(
        fixture_position=np.array([0.0, -5.0, 6.5]),
        stage_origin=np.array([0.0, 0.0, 0.0])
    )
    
    # Add front camera
    vis.add_camera(
        camera_id="front_reid",
        position=np.array([0.0, 0.0, 2.5]),
        rotation=np.array([0.0, 0.0, 0.0]),
        fov=60.0
    )
    
    return vis


def main():
    """Main entry point for standalone 3D visualization."""
    import argparse
    
    parser = argparse.ArgumentParser(description="3D Visualization for Followspot System")
    parser.add_argument("--backend", choices=["matplotlib", "pyqtgraph"], 
                       default="matplotlib", help="Visualization backend")
    parser.add_argument("--config", help="Path to config JSON")
    parser.add_argument("--demo", action="store_true", help="Run demo mode with simulated data")
    
    args = parser.parse_args()
    
    if not MATPLOTLIB_AVAILABLE and not PYQTGRAPH_AVAILABLE:
        print("Error: No visualization backend available. Install matplotlib or pyqtgraph.")
        return 1
    
    # Create visualization
    vis = create_default_visualization()
    
    if args.demo:
        # Run with simulated data
        import threading
        
        def demo_loop():
            t = 0
            while True:
                # Simulate person moving in a circle
                for i in range(3):
                    x = 3 * math.cos(t + i * 2 * math.pi / 3)
                    y = 3 * math.sin(t + i * 2 * math.pi / 3)
                    z = 1.75
                    vis.update_person(i, np.array([x, y, z]))
                
                # Simulate spotlight following person 0
                pos = vis.persons.get(0)
                if pos:
                    dx = pos.position[0] - 0
                    dy = pos.position[1] - (-5)
                    dz = pos.position[2] - 6.5
                    pan = math.degrees(math.atan2(dx, dy))
                    tilt = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
                    vis.update_spotlight(0, pan, tilt)
                
                t += 0.1
                time.sleep(0.1)
        
        demo_thread = threading.Thread(target=demo_loop, daemon=True)
        demo_thread.start()
    
    # Run visualization
    try:
        if MATPLOTLIB_AVAILABLE:
            vis.run_matplotlib()
        else:
            print("No visualization backend available")
            return 1
    except KeyboardInterrupt:
        pass
    
    return 0


if __name__ == "__main__":
    sys.exit(main())