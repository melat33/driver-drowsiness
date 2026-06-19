"""
alerts.py — Audio and Telegram alert system with cooldown.

Two channels:
  1. Local audio via pygame (plays alert.wav when score exceeds threshold)
  2. Remote Telegram message via Bot API (fires at DANGER level)

Both channels share the same cooldown timer to prevent alert spam.
"""

import time
import threading
import requests

import config


class AlertSystem:
    """
    Thread-safe alert dispatcher with configurable cooldown.

    Usage:
        alerts = AlertSystem()
        alerts.check_and_fire(score, status, state_dict)
    """

    def __init__(self):
        self._last_audio_alert    = 0.0
        self._last_telegram_alert = 0.0
        self._lock                = threading.Lock()
        self._pygame_ready        = False
        self._init_pygame()

    def _init_pygame(self) -> None:
        """Initialise pygame mixer — gracefully skip if unavailable."""
        try:
            import pygame
            pygame.mixer.init()
            self._pygame = pygame
            self._pygame_ready = True
        except Exception:
            self._pygame_ready = False

    # ── Public API ────────────────────────────────────────────────────────────

    def check_and_fire(self, score: float, status: str) -> None:
        """
        Called once per frame by the Flask /status route consumer.
        Fires alerts if score and cooldown conditions are met.
        """
        now = time.time()

        if score >= config.ALERT_SCORE_TRIGGER:
            self._maybe_play_audio(now)

        if status == "DANGER" and config.TELEGRAM_ENABLED:
            self._maybe_send_telegram(now, score)

    def fire_test(self) -> dict:
        """Force-fire both channels (used by /test-alert route)."""
        self._play_audio()
        result = {"audio": self._pygame_ready}
        if config.TELEGRAM_ENABLED:
            result["telegram"] = self._send_telegram(99.0)
        return result

    # ── Audio ─────────────────────────────────────────────────────────────────

    def _maybe_play_audio(self, now: float) -> None:
        with self._lock:
            elapsed = now - self._last_audio_alert
            if elapsed < config.ALERT_COOLDOWN_SEC:
                return
            self._last_audio_alert = now

        # Run on a thread so it never blocks the engine loop.
        threading.Thread(target=self._play_audio, daemon=True).start()

    def _play_audio(self) -> None:
        if not self._pygame_ready:
            return
        try:
            sound = self._pygame.mixer.Sound(config.ALERT_SOUND_FILE)
            sound.play()
            # Block this thread until the sound finishes, not the main thread.
            self._pygame.time.wait(int(sound.get_length() * 1000))
        except Exception:
            pass

    # ── Telegram ──────────────────────────────────────────────────────────────

    def _maybe_send_telegram(self, now: float, score: float) -> None:
        with self._lock:
            elapsed = now - self._last_telegram_alert
            if elapsed < config.ALERT_COOLDOWN_SEC:
                return
            self._last_telegram_alert = now

        threading.Thread(
            target=self._send_telegram,
            args=(score,),
            daemon=True,
        ).start()

    def _send_telegram(self, score: float) -> bool:
        """
        Send a Telegram message via the Bot API.
        Returns True on success, False on failure.
        """
        if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
            return False

        url     = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        message = (
            f"🚨 DRIVER ALERT — Fatigue Score: {score:.0f}/100\n"
            f"Status: DANGER\n"
            f"Immediate attention required!"
        )
        try:
            resp = requests.post(
                url,
                json={"chat_id": config.TELEGRAM_CHAT_ID, "text": message},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False