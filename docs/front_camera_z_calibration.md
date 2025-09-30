# Front Camera Z-Calibration Playbook

A quick, projection-free workflow for calibrating the front ReID camera so it supplies reliable Z data for spotlight tilt.

> **TL;DR:** Grab a tape measure and an inclinometer (A phone level works fine), enter the numbers into the configurator, then confirm the camera/stage axes agree.
---

## 1. Prep the Stage (5 min)

1. Pick a stage origin. The default system assumes:
   - $X$ grows to stage right
   - $Y$ grows upstage
   - $Z$ grows upward from the deck
   Put the origin wherever is convenient (front-center, downstage-left, etc.).
2. Measure the stage width, depth, and height. These inform the safety envelope and grid overlays.
3. Mark the four stage corners with tape so they’re easy to click later in the preview.

## 2. Measure the Camera Pose (10 min)

| Measurement | How to get it | Where it lives |
| --- | --- | --- |
| Horizontal offset from origin $(X, Y)$ | Tape measure on the deck | `Front Node Settings → Camera Position` |
| Height $(Z)$ | Laser rangefinder or tape to the lens center | `Camera Position` |
| Pitch (downward tilt) | Inclinometer/phone level on camera body | `Camera Angle (deg)` |
| Yaw (left/right) | Measure angle to face downstage; optional if camera square | Rotation matrix (only if yaw ≠ 0) |

Enter these values in the **Front Node Settings** tab and hit **Save Configuration** right away so you don’t lose them.

## 3. Capture Stage Corners (2 min)

1. Start the live preview in the configurator.
2. Click **Calibrate**, then click each stage corner when prompted (front-left → front-right → back-right → back-left).
3. The configurator records the pixel coordinates and timestamps the run. No fiducials needed—your taped corners are enough.

## 4. Confirm the Pose with Actors (or a Stand-In)

1. Launch the fused loop (`python control/fused_main.py`) or start the show profile from the launcher.
2. Walk a stand-in to the stage origin. The fused position should hover near $(0, 0)$.
3. Send them upstage ~1 m; the reported $Y$ should climb by ≈1.0.
4. Have a tall and short person compare Z readouts. They don’t need to be exact heights, just trending upward with taller subjects.

If values are mirrored or sign-flipped, adjust the rotation matrix:
- Flip $Y$ by multiplying the second column by $-1$.
- Swap axes if $X$/$Y$ are swapped.

## 5. Sync the Spotlight Rig (3 min)

1. Open the **Spotlight Rig** tab.
2. Enter the fixture position relative to the same origin you used for the stage/camera.
3. Set pan/tilt zero angles so the fixture points at the origin when both are zero.
4. Save again—this writes `config/spotlight_config.json` alongside the front camera config.

## 6. Maintenance Tips

- Recheck measurements after any rigging change or if the camera mount drifts.
- Save copies of the calibrated JSON files in `backups/` once you’re satisfied.
- Use the **Test System** button in the configurator before every show day for a quick sanity check.

---

## Optional: High-Precision Photogrammetry (Advanced)

This is a feature that I will look to incorperating if I find in my testing that sub centimeter precision is needed, for example on a rig very high up. 
