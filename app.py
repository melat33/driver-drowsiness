"""
app.py — Flask server and camera thread.

Three responsibilities:
  1. Camera thread: reads frames from webcam, draws facial overlays,
     pushes frames to both the MJPEG queue and the engine queue.
  2. Fatigue engine: runs in its own thread (imported from detector/).
  3. Flask routes: serve the dashboard and JSON API endpoints.

Threading layout:
  Main thread       → Flask (serves HTTP)
  camera_thread     → reads frames, draws overlays, pushes to queues
  FatigueEngine     → pops frames, runs metrics, updates shared_state
  AlertSystem       → fires on demand (no dedicated thread; uses short-lived threads)
"""

import queue
import threading
import time
import cv2

from flask import Flask, Response, jsonify, render_template, send_file
import io

import config
from detector.fatigue_engine import FatigueEngine
from detector.alerts import AlertSystem
from utils.logger import EventLogger
from utils.exporter import build_csv_from_log, build_csv_from_events


# ── Shared state ──────────────────────────────────────────────────────────────

shared_state: dict  = {"state": None}
state_lock          = threading.Lock()

# Engine queue: frames for fatigue scoring (small — we only want latest frame)
engine_queue: queue.Queue = queue.Queue(maxsize=2)

# MJPEG queue: encoded JPEG frames for the video stream
mjpeg_queue: queue.Queue  = queue.Queue(maxsize=5)


# ── Subsystems ────────────────────────────────────────────────────────────────

engine  = FatigueEngine(engine_queue, shared_state, state_lock)
alerts  = AlertSystem()
logger  = EventLogger()


# ── Camera thread ─────────────────────────────────────────────────────────────

def camera_thread() -> None:
    """
    Reads frames from the webcam, draws minimal overlay annotations,
    encodes to JPEG, and pushes to both queues.

    Overlay drawn here (not in the engine) so the video stream always
    shows live data without waiting for the engine to process each frame.
    """
    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          config.FPS_TARGET)

    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue

        # ── Push raw frame to engine (drop if full — prefer freshness) ────────
        if not engine_queue.full():
            engine_queue.put_nowait(frame.copy())

        # ── Draw overlay from latest shared state ─────────────────────────────
        with state_lock:
            state = shared_state.get("state")

        annotated = _draw_overlay(frame, state)

        # ── Encode to JPEG and push to MJPEG queue ────────────────────────────
        _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not mjpeg_queue.full():
            mjpeg_queue.put_nowait(jpeg.tobytes())

    cap.release()


def _draw_overlay(frame: "np.ndarray", state) -> "np.ndarray":
    """
    Draw minimal HUD overlay on the frame.
    Keeps text in the top-left corner, matching Jasper's reference style.
    """
    if state is None:
        return frame

    s = state

    # Choose colour based on status
    colour_map = {"NORMAL": (0, 255, 0), "DROWSY": (0, 165, 255), "DANGER": (0, 0, 255)}
    colour     = colour_map.get(s.status, (255, 255, 255))
    font       = cv2.FONT_HERSHEY_SIMPLEX

    lines = [
        (f"EAR: {s.ear:.3f}",             (10, 30),  0.6, (255, 255, 0)),
        (f"Closed Frames: {s.blinks}",     (10, 55),  0.55, (0, 255, 0)),
        (f"MAR: {s.mar:.3f}",             (10, 85),  0.6, (0, 140, 255)),
        (f"Yawns (5min): {s.yawns_recent}/{s.yawns}", (10, 110), 0.55, (0, 140, 255)),
        (f"Yaw: {s.yaw:.1f}",             (10, 135), 0.55, (255, 0, 255)),
        (f"Pitch: {s.pitch:.1f}",         (10, 160), 0.55, (255, 0, 255)),
        (f"Fatigue Score: {s.fatigue_score:.0f}", (10, 190), 0.65, colour),
        (f"Status: {s.status}",            (10, 220), 0.75, colour),
    ]

    for text, pos, scale, col in lines:
        cv2.putText(frame, text, pos, font, scale, col, 2, cv2.LINE_AA)

    if s.no_face:
        cv2.putText(frame, "NO FACE DETECTED", (150, 240), font, 0.9, (0, 0, 255), 2)

    # Corner brackets (matches reference image style)
    h, w = frame.shape[:2]
    blen = 20
    bt   = 2
    cv2.line(frame, (0, 0),       (blen, 0),    (0, 255, 0), bt)
    cv2.line(frame, (0, 0),       (0, blen),    (0, 255, 0), bt)
    cv2.line(frame, (w-blen, 0),  (w, 0),       (0, 255, 0), bt)
    cv2.line(frame, (w, 0),       (w, blen),    (0, 255, 0), bt)
    cv2.line(frame, (0, h-blen),  (0, h),       (0, 255, 0), bt)
    cv2.line(frame, (0, h),       (blen, h),    (0, 255, 0), bt)
    cv2.line(frame, (w-blen, h),  (w, h),       (0, 255, 0), bt)
    cv2.line(frame, (w, h-blen),  (w, h),       (0, 255, 0), bt)

    return frame


# ── MJPEG generator ───────────────────────────────────────────────────────────

def _mjpeg_generator():
    """
    Yield a multipart/x-mixed-replace stream of JPEG frames.
    The browser <img src="/video_feed"> tag renders this as live video.
    """
    while True:
        try:
            jpeg = mjpeg_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + jpeg +
            b"\r\n"
        )


# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/video_feed")
def video_feed():
    """MJPEG stream — consumed by <img src="/video_feed"> in dashboard."""
    return Response(
        _mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/status")
def status():
    """
    JSON snapshot of current driver state.
    Dashboard polls this every 1 second to update all metrics.
    """
    with state_lock:
        state = shared_state.get("state")

    if state is None:
        return jsonify({"status": "INITIALISING", "fatigue_score": 0})

    data = state.to_dict()

    # Fire alerts (non-blocking — AlertSystem uses short-lived threads)
    alerts.check_and_fire(data["fatigue_score"], data["status"], data.get("yawns_recent", 0))

    # Log state transitions
    logger.check_and_log(data)

    return jsonify(data)


@app.route("/events")
def events():
    """Recent event log — consumed by the dashboard event table."""
    return jsonify(logger.recent(50))


@app.route("/export")
def export():
    """Download full session log as CSV."""
    csv_data = build_csv_from_log() or build_csv_from_events(logger.recent(200))
    buf = io.BytesIO(csv_data.encode("utf-8"))
    buf.seek(0)
    filename = f"drowsiness_session_{int(time.time())}.csv"
    return send_file(
        buf,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/test-alert")
def test_alert():
    """Dev route: force-fire audio + Telegram to verify setup."""
    result = alerts.fire_test()
    return jsonify({"fired": True, "channels": result})


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Start engine and camera threads before Flask begins serving
    engine.start()
    cam = threading.Thread(target=camera_thread, daemon=True, name="Camera")
    cam.start()

    print(f"Dashboard → http://localhost:{config.FLASK_PORT}")
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
        threaded=True,
        use_reloader=False,   # reloader would start two camera threads
    )
