import os
from dotenv import load_dotenv

load_dotenv()

# ── Camera ────────────────────────────────────────────────────────────────────
CAMERA_INDEX = 0
FRAME_WIDTH  = 640
FRAME_HEIGHT = 480
FPS_TARGET   = 30

# ── EAR (Eye Aspect Ratio) ────────────────────────────────────────────────────
# Eyes are considered "closed" when EAR drops below this value.
# Typical open-eye EAR: 0.25–0.32. Closed: < 0.20.
EAR_THRESHOLD        = 0.20
# How many consecutive closed-eye frames before we register a "closure event".
# At 30fps, 20 frames ≈ 0.67 seconds — long enough to skip normal blinks.
EAR_CONSEC_FRAMES    = 20

# ── MAR (Mouth Aspect Ratio) ──────────────────────────────────────────────────
# MAR rises above this during a yawn.
MAR_THRESHOLD        = 0.60
MAR_CONSEC_FRAMES    = 15

# ── Head Pose ─────────────────────────────────────────────────────────────────
YAW_THRESHOLD        = 25.0
PITCH_THRESHOLD      = -15.0
ROLL_THRESHOLD       = 20.0
POSE_CONSEC_FRAMES   = 10

# ── Microsleep (sudden head drop) ────────────────────────────────────────────
HEAD_DROP_DELTA      = 8.0
HEAD_DROP_WINDOW     = 5

# ── Fatigue Score Weights (must sum to 1.0) ───────────────────────────────────
WEIGHT_EAR           = 0.35
WEIGHT_MAR           = 0.20
WEIGHT_POSE          = 0.30
WEIGHT_DROP          = 0.15

# ── State Thresholds ─────────────────────────────────────────────────────────
SCORE_DROWSY         = 40
SCORE_DANGER         = 70

# ── Alert System ─────────────────────────────────────────────────────────────
ALERT_COOLDOWN_SEC   = 30
ALERT_SOUND_FILE     = "static/audio/alert.wav"
ALERT_SCORE_TRIGGER  = SCORE_DROWSY

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_ENABLED       = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
TELEGRAM_BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID       = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_SCORE_TRIGGER = SCORE_DANGER

# ── Event Logging ─────────────────────────────────────────────────────────────
LOG_DIR              = "logs"
LOG_FILE             = "logs/session.jsonl"
MAX_EVENTS_IN_MEMORY = 200

# ── Flask ─────────────────────────────────────────────────────────────────────
FLASK_HOST           = "0.0.0.0"
FLASK_PORT           = 5000
FLASK_DEBUG          = os.getenv("FLASK_DEBUG", "false").lower() == "true"