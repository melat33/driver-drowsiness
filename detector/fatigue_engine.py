"""
fatigue_engine.py — Stateful fatigue scoring and classification.

This is the heart of the system. It:
  1. Maintains rolling counters (consecutive closed frames, yawn frames, etc.)
  2. Fuses EAR, MAR, head pose, and head drop into a single 0–100 fatigue score
  3. Classifies the score into NORMAL / DROWSY / DANGER
  4. Runs in its own background thread, writing to a shared state dict

Threading model:
  - The engine loop runs in a daemon thread (started by app.py).
  - It reads frames from a queue filled by the camera thread.
  - Flask routes read from `shared_state` — a plain dict protected by a Lock.
  - No Flask code lives here; the engine is fully independent.
"""

import threading
import time
import queue
from collections import deque
from dataclasses import dataclass, field, asdict

import numpy as np

import config
from detector.face_mesh import FaceMeshDetector
from detector.metrics import (
    compute_avg_ear,
    compute_mar,
    compute_head_pose,
    detect_head_drop,
)


# ── State dataclass ───────────────────────────────────────────────────────────

@dataclass
class DriverState:
    """Snapshot of the driver's condition at one point in time."""
    ear:           float = 0.0
    mar:           float = 0.0
    yaw:           float = 0.0
    pitch:         float = 0.0
    roll:          float = 0.0
    fatigue_score: float = 0.0
    status:        str   = "NORMAL"   # "NORMAL" | "DROWSY" | "DANGER"
    blinks:        int   = 0
    yawns:         int   = 0
    head_drops:    int   = 0
    alerts_fired:  int   = 0
    no_face:       bool  = False
    timestamp:     float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ear"]           = round(d["ear"], 3)
        d["mar"]           = round(d["mar"], 3)
        d["yaw"]           = round(d["yaw"], 1)
        d["pitch"]         = round(d["pitch"], 1)
        d["roll"]          = round(d["roll"], 1)
        d["fatigue_score"] = round(d["fatigue_score"], 1)
        return d


# ── Fatigue Engine ────────────────────────────────────────────────────────────

class FatigueEngine:
    """
    Stateful engine that processes frames from a queue and maintains
    the current DriverState in a thread-safe shared dict.
    """

    def __init__(self, frame_queue: queue.Queue, shared_state: dict, state_lock: threading.Lock):
        self._queue       = frame_queue
        self._shared      = shared_state
        self._lock        = state_lock
        self._running     = False

        # Rolling counters
        self._consec_closed  = 0   # frames where EAR < threshold
        self._consec_yawn    = 0   # frames where MAR > threshold
        self._consec_pose    = 0   # frames where head pose is off

        # Session totals
        self._blinks     = 0
        self._yawns      = 0
        self._drops      = 0
        self._alerts     = 0

        # Pitch history for head-drop detection
        self._pitch_history: deque[float] = deque(maxlen=config.HEAD_DROP_WINDOW + 2)

        # Face mesh detector (lives on this thread)
        self._detector = FaceMeshDetector()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch the engine loop in a daemon thread."""
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True, name="FatigueEngine")
        t.start()

    def stop(self) -> None:
        self._running = False
        self._detector.close()

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            try:
                frame_bgr = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            state = self._process_frame(frame_bgr)

            with self._lock:
                self._shared["state"] = state

    def _process_frame(self, frame_bgr: np.ndarray) -> DriverState:
        import cv2
        frame_rgb  = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w       = frame_bgr.shape[:2]
        landmarks  = self._detector.process(frame_rgb)

        if landmarks is None:
            return DriverState(
                no_face=True,
                blinks=self._blinks,
                yawns=self._yawns,
                head_drops=self._drops,
                alerts_fired=self._alerts,
            )

        # ── Extract signals ───────────────────────────────────────────────────
        ear               = compute_avg_ear(landmarks)
        mar               = compute_mar(landmarks)
        yaw, pitch, roll  = compute_head_pose(landmarks, w, h)

        self._pitch_history.append(pitch)
        head_drop = detect_head_drop(
            list(self._pitch_history),
            config.HEAD_DROP_WINDOW,
            config.HEAD_DROP_DELTA,
        )

        # ── Update counters ───────────────────────────────────────────────────
        ear_score  = self._update_ear(ear)
        mar_score  = self._update_mar(mar)
        pose_score = self._update_pose(yaw, pitch)
        drop_score = self._update_drop(head_drop)

        # ── Compute fatigue score ─────────────────────────────────────────────
        # Each sub-score is 0.0–1.0; weighted sum then scaled to 0–100.
        raw = (
            ear_score  * config.WEIGHT_EAR  +
            mar_score  * config.WEIGHT_MAR  +
            pose_score * config.WEIGHT_POSE +
            drop_score * config.WEIGHT_DROP
        )
        fatigue_score = min(raw * 100.0, 100.0)

        # ── Classify ──────────────────────────────────────────────────────────
        if fatigue_score >= config.SCORE_DANGER:
            status = "DANGER"
        elif fatigue_score >= config.SCORE_DROWSY:
            status = "DROWSY"
        else:
            status = "NORMAL"

        return DriverState(
            ear=ear, mar=mar,
            yaw=yaw, pitch=pitch, roll=roll,
            fatigue_score=fatigue_score,
            status=status,
            blinks=self._blinks,
            yawns=self._yawns,
            head_drops=self._drops,
            alerts_fired=self._alerts,
        )

    # ── Sub-scorers (each returns 0.0–1.0) ───────────────────────────────────

    def _update_ear(self, ear: float) -> float:
        """
        Returns 1.0 if eyes have been closed for >= EAR_CONSEC_FRAMES.
        Increments blink counter when a closure event ends.
        """
        if ear < config.EAR_THRESHOLD:
            self._consec_closed += 1
        else:
            if self._consec_closed >= config.EAR_CONSEC_FRAMES:
                self._blinks += 1
            self._consec_closed = 0

        if self._consec_closed >= config.EAR_CONSEC_FRAMES:
            # Scale: longer closure → higher score, capped at 1.0.
            return min(self._consec_closed / (config.EAR_CONSEC_FRAMES * 2), 1.0)
        return 0.0

    def _update_mar(self, mar: float) -> float:
        """Returns proportional score for mouth openness above threshold."""
        if mar > config.MAR_THRESHOLD:
            self._consec_yawn += 1
        else:
            if self._consec_yawn >= config.MAR_CONSEC_FRAMES:
                self._yawns += 1
            self._consec_yawn = 0

        if self._consec_yawn >= config.MAR_CONSEC_FRAMES:
            return min((mar - config.MAR_THRESHOLD) / 0.4, 1.0)
        return 0.0

    def _update_pose(self, yaw: float, pitch: float) -> float:
        """Returns score based on how far head pose deviates from forward-facing."""
        off_pose = (
            abs(yaw)   > config.YAW_THRESHOLD or
            pitch      < config.PITCH_THRESHOLD
        )
        if off_pose:
            self._consec_pose += 1
        else:
            self._consec_pose = 0

        if self._consec_pose >= config.POSE_CONSEC_FRAMES:
            yaw_excess   = max(0, abs(yaw)   - config.YAW_THRESHOLD)
            pitch_excess = max(0, abs(pitch) - abs(config.PITCH_THRESHOLD))
            return min((yaw_excess + pitch_excess) / 30.0, 1.0)
        return 0.0

    def _update_drop(self, drop: bool) -> float:
        """Binary: head drop detected → 1.0, else 0.0. Increments counter."""
        if drop:
            self._drops += 1
            return 1.0
        return 0.0