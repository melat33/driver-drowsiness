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
# MAR rises above this during a yawn. Using outer-lip landmarks now —
# resting baseline is ~0.15-0.30, so the yawn threshold sits higher than before.
MAR_THRESHOLD        = 0.55
MAR_CONSEC_FRAMES    = 15

# ── Head Pose ─────────────────────────────────────────────────────────────────
YAW_THRESHOLD        = 25.0
PITCH_THRESHOLD      = -15.0
ROLL_THRESHOLD       = 20.0
POSE_CONSEC_FRAMES   = 10

# ── Microsleep (sudden head drop) ────────────────────────────────────────────
# Delta pitch (degrees) measured over HEAD_DROP_WINDOW frames.
# Raised from 8.0 -> 18.0 and window 5 -> 8 frames: normal head bob/mouth
# movement was triggering this every ~1.5s at the old sensitivity.
HEAD_DROP_DELTA      = 18.0
HEAD_DROP_WINDOW     = 8
# Minimum seconds between two counted head-drop events (debounce).
HEAD_DROP_COOLDOWN_SEC = 2.0

# ── Yawn-count based fatigue (NEW) ────────────────────────────────────────────
# Independent of momentary MAR — escalates fatigue based on how many
# yawns have accumulated in the session, since repeated yawning is itself
# a strong fatigue signal even if each individual yawn is brief.
YAWN_COUNT_DROWSY    = 3    # 3+ yawns in session -> contributes to DROWSY
YAWN_COUNT_DANGER    = 6    # 6+ yawns in session -> contributes to DANGER
# Rolling window: only count yawns from the last N seconds (avoids an old
# yawn from 20 minutes ago still inflating the score).
YAWN_WINDOW_SEC      = 300  # 5 minutes

# ── Fatigue Score Weights (must sum to 1.0) ───────────────────────────────────
WEIGHT_EAR           = 0.30
WEIGHT_MAR           = 0.15   # momentary mouth openness (current frame)
WEIGHT_YAWN_COUNT    = 0.15   # cumulative yawns this session (NEW)
WEIGHT_POSE          = 0.25
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