import cv2
import numpy as np

def analyze_ir_beacons(self, frame):
    # Convert to grayscale if not already
    if len(frame.shape) == 3:
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray_frame = frame
    
    # Apply threshold to isolate bright spots (potential IR beacons)
    _, thresholded = cv2.threshold(gray_frame, self.threshold, 255, cv2.THRESH_BINARY)
    
    # Find contours in the thresholded image
    contours, _ = cv2.findContours(thresholded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    beacons = []
    for contour in contours:
        # Calculate center of contour
        M = cv2.moments(contour)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            
            # Calculate area
            area = cv2.contourArea(contour)
            
            # Add beacon information to list if area meets minimum size
            if area > 10:  # Filter out noise
                beacons.append({
                    "center": (cx, cy),
                    "area": area
                })
    
    return beacons

def visualize_ir_beacons(self, frame, beacons):
    """
    Create a visualization of IR beacons as white dots on a black background
    """
    # Create a black image with the same dimensions as the input frame
    visualization = np.zeros((frame.shape[0], frame.shape[1]), dtype=np.uint8)
    
    # Draw white dots at beacon locations
    for beacon in beacons:
        center = beacon["center"]
        # Draw a filled circle (dot) at the center of each beacon
        cv2.circle(visualization, center, 5, 255, -1)  # radius 5, white color, filled
    
    return visualization

def process_frame(self, frame):
    """
    Process a frame to detect and visualize IR beacons
    """
    beacons = self.analyze_ir_beacons(frame)
    visualization = self.visualize_ir_beacons(frame, beacons)
    return beacons, visualization
