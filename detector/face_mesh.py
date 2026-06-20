"""
face_mesh.py — MediaPipe Face Mesh wrapper.

Keeps all MediaPipe logic in one place so the rest of the codebase
never imports mediapipe directly. If we ever swap MediaPipe for a
different landmark model, only this file changes.
"""

import numpy as np
import mediapipe as mp


class FaceMeshDetector:
    """
    Wraps MediaPipe Face Mesh and exposes a single `process` method
    that returns a (N, 2) numpy array of pixel-space landmark coordinates,
    or None if no face is detected.
    """

    def __init__(
        self,
        max_faces: int = 1,
        refine_landmarks: bool = True,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        self._mp_face_mesh = mp.solutions.face_mesh
        self._face_mesh = self._mp_face_mesh.FaceMesh(
            max_num_faces=max_faces,
            refine_landmarks=refine_landmarks,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def process(
        self,
        frame_rgb: np.ndarray,
    ) -> np.ndarray | None:
        """
        Run face mesh detection on an RGB frame.

        Args:
            frame_rgb: (H, W, 3) uint8 numpy array in RGB colour order.
                       OpenCV reads in BGR — caller must convert with
                       cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) first.

        Returns:
            (468, 2) array of (x, y) pixel coordinates if a face is found,
            or None if no face is detected.

        Note:
            MediaPipe returns normalised coordinates (0.0–1.0). We convert
            to pixel space here so every downstream function can work in
            pixel coordinates without knowing the frame dimensions.
        """
        results = self._face_mesh.process(frame_rgb)

        if not results.multi_face_landmarks:
            return None

        # Take the first (and typically only) detected face.
        face_landmarks = results.multi_face_landmarks[0]
        h, w = frame_rgb.shape[:2]

        landmarks = np.array(
            [(lm.x * w, lm.y * h) for lm in face_landmarks.landmark],
            dtype=np.float64,
        )
        return landmarks

    def close(self) -> None:
        """Release MediaPipe resources."""
        self._face_mesh.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
