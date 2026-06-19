"""
metrics.py — Pure signal extraction functions.

Every function here takes only numpy arrays or floats — no OpenCV, no MediaPipe,
no side effects. This makes them trivially testable in isolation.

MediaPipe landmark indices used:
  Left eye:  [33, 160, 158, 133, 153, 144]
  Right eye: [362, 385, 387, 263, 373, 380]
  Mouth:     [61, 291, 13, 14, 17, 0]  (outer lips + inner vertical)
"""

import math
import numpy as np


# ── Landmark index constants ──────────────────────────────────────────────────

LEFT_EYE_IDX  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]
MOUTH_IDX     = [61, 291, 13, 14, 17, 0]

# 3D model points of a generic human face (used by solvePnP for head pose).
# These are world-space coordinates in millimetres, chosen to match the
# MediaPipe face mesh layout.
FACE_3D_MODEL = np.array([
    [0.0,    0.0,    0.0],    # Nose tip (index 1)
    [0.0,   -330.0, -65.0],   # Chin (index 152)
    [-225.0, 170.0, -135.0],  # Left eye left corner (index 33)
    [225.0,  170.0, -135.0],  # Right eye right corner (index 263)
    [-150.0, -150.0, -125.0], # Left mouth corner (index 61)
    [150.0,  -150.0, -125.0], # Right mouth corner (index 291)
], dtype=np.float64)

# MediaPipe landmark indices matching the 3D model points above.
POSE_LANDMARK_IDX = [1, 152, 33, 263, 61, 291]


# ── Euclidean distance helper ─────────────────────────────────────────────────

def _dist(p1: np.ndarray, p2: np.ndarray) -> float:
    """Euclidean distance between two 2D or 3D points."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


# ── EAR ───────────────────────────────────────────────────────────────────────

def compute_ear(landmarks: np.ndarray, eye_indices: list[int]) -> float:
    """
    Eye Aspect Ratio (Soukupová & Čech, 2016).

    The six landmark points around one eye:
        p1 (left corner) — p2 (top-left) — p3 (top-right)
        p4 (right corner) — p5 (bottom-right) — p6 (bottom-left)

    EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)

    When open:  ~0.25–0.32
    When closed: drops toward 0

    Args:
        landmarks: (N, 2) array of (x, y) pixel coordinates for all face landmarks.
        eye_indices: list of 6 landmark indices in the order [p1..p6].

    Returns:
        EAR as a float.
    """
    p = [landmarks[i] for i in eye_indices]
    vertical_1 = _dist(p[1], p[5])
    vertical_2 = _dist(p[2], p[4])
    horizontal = _dist(p[0], p[3])
    if horizontal == 0:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)


def compute_avg_ear(landmarks: np.ndarray) -> float:
    """Average EAR across both eyes."""
    left  = compute_ear(landmarks, LEFT_EYE_IDX)
    right = compute_ear(landmarks, RIGHT_EYE_IDX)
    return (left + right) / 2.0


# ── MAR ───────────────────────────────────────────────────────────────────────

def compute_mar(landmarks: np.ndarray) -> float:
    """
    Mouth Aspect Ratio — mirrors the EAR formula applied to mouth landmarks.

    Indices used (from MOUTH_IDX = [61, 291, 13, 14, 17, 0]):
        p1 = left corner  (61)
        p2 = right corner (291)
        p3 = upper lip top (13)
        p4 = lower lip bottom (14)
        p5 = chin point (17)     [not used in formula, kept for completeness]
        p6 = upper outer lip (0)

    MAR = |p3-p4| / |p1-p2|

    At rest: ~0.02–0.10. During yawn: spikes above 0.60.

    Args:
        landmarks: (N, 2) array of pixel coordinates.

    Returns:
        MAR as a float.
    """
    p = [landmarks[i] for i in MOUTH_IDX]
    vertical   = _dist(p[2], p[3])   # upper-lip to lower-lip
    horizontal = _dist(p[0], p[1])   # left corner to right corner
    if horizontal == 0:
        return 0.0
    return vertical / horizontal


# ── Head Pose ─────────────────────────────────────────────────────────────────

def compute_head_pose(
    landmarks: np.ndarray,
    frame_w: int,
    frame_h: int,
) -> tuple[float, float, float]:
    """
    Estimate head pose (yaw, pitch, roll) in degrees using OpenCV solvePnP.

    How it works:
      1. We know where 6 key landmarks appear in the 2D image (from MediaPipe).
      2. We know where those same 6 points sit on a generic 3D face model.
      3. solvePnP solves for the rotation matrix R that maps model → image.
      4. We decompose R into Euler angles: yaw (left/right), pitch (up/down), roll (tilt).

    Args:
        landmarks: (N, 2) array of pixel coordinates.
        frame_w:   frame width in pixels (needed to build camera matrix).
        frame_h:   frame height in pixels.

    Returns:
        (yaw, pitch, roll) tuple in degrees.
        Positive yaw  = head turned right.
        Negative pitch = head tilted forward/down.
    """
    import cv2  # imported here so metrics.py stays importable without OpenCV

    image_points = np.array(
        [landmarks[i] for i in POSE_LANDMARK_IDX],
        dtype=np.float64,
    )

    # Approximate camera intrinsics (no calibration file needed).
    focal_length = frame_w
    center       = (frame_w / 2, frame_h / 2)
    camera_matrix = np.array([
        [focal_length, 0,            center[0]],
        [0,            focal_length, center[1]],
        [0,            0,            1        ],
    ], dtype=np.float64)

    dist_coeffs = np.zeros((4, 1))  # assuming no lens distortion

    success, rotation_vec, _ = cv2.solvePnP(
        FACE_3D_MODEL,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )

    if not success:
        return 0.0, 0.0, 0.0

    rotation_mat, _ = cv2.Rodrigues(rotation_vec)

    # Decompose rotation matrix into Euler angles (in radians, then convert).
    sy = math.sqrt(rotation_mat[0, 0] ** 2 + rotation_mat[1, 0] ** 2)
    singular = sy < 1e-6

    if not singular:
        roll  =  math.atan2( rotation_mat[2, 1], rotation_mat[2, 2])
        pitch =  math.atan2(-rotation_mat[2, 0], sy)
        yaw   =  math.atan2( rotation_mat[1, 0], rotation_mat[0, 0])
    else:
        roll  =  math.atan2(-rotation_mat[1, 2], rotation_mat[1, 1])
        pitch =  math.atan2(-rotation_mat[2, 0], sy)
        yaw   =  0.0

    yaw_deg   = math.degrees(yaw)
    pitch_deg = math.degrees(pitch)
    roll_deg  = math.degrees(roll)

    return yaw_deg, pitch_deg, roll_deg


# ── Head Drop (microsleep detector) ───────────────────────────────────────────

def detect_head_drop(
    pitch_history: list[float],
    window: int,
    delta_threshold: float,
) -> bool:
    """
    Detect a sudden forward head drop by measuring pitch change over a window.

    A normal head movement is gradual. A microsleep head drop is sudden —
    pitch can change 8–15 degrees in just a few frames.

    Args:
        pitch_history: list of recent pitch values (newest last).
        window:        number of frames to look back.
        delta_threshold: minimum pitch drop (degrees) to flag as a drop.

    Returns:
        True if a sudden drop is detected.
    """
    if len(pitch_history) < window:
        return False
    recent   = pitch_history[-window:]
    delta    = recent[-1] - recent[0]   # negative = head dropped forward
    return delta < -abs(delta_threshold)