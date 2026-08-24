from __future__ import annotations

import threading
import time
from typing import Any

import requests

from .user_language import telegram_plain_text


class TelegramNotifier:
    def __init__(
        self,
        token: str = "",
        chat_id: str = "",
        *,
        enabled: bool = False,
        timeout: float = 5.0,
    ) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self._lock = threading.RLock()
        self._last_sent: dict[str, float] = {}
        self.token = ""
        self.chat_id = ""
        self.enabled = False
        self.configure(token=token, chat_id=chat_id, enabled=enabled)

    def configure(self, *, token: str, chat_id: str, enabled: bool) -> None:
        with self._lock:
            self.token = token.strip()
            self.chat_id = chat_id.strip()
            self.enabled = bool(enabled and self.token and self.chat_id)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "configured": bool(self.token and self.chat_id),
                "token_configured": bool(self.token),
                "chat_id": self.chat_id,
                "automatic_alerts": "buy_candidate_only",
            }

    def send(
        self,
        text: str,
        *,
        event_key: str = "",
        min_interval_seconds: float = 0.0,
        disable_notification: bool = False,
    ) -> bool:
        with self._lock:
            token = self.token
            chat_id = self.chat_id
            enabled = self.enabled

        if not enabled:
            return False

        now = time.time()
        if event_key:
            with self._lock:
                last = self._last_sent.get(event_key, 0.0)
                if now - last < min_interval_seconds:
                    return False

        friendly_text = telegram_plain_text(text)
        response = self.session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": friendly_text,
                "disable_web_page_preview": "true",
                "disable_notification": "true" if disable_notification else "false",
            },
            timeout=self.timeout,
        )
        if not response.ok:
            description = "request failed"
            try:
                description = str(response.json().get("description") or description)
            except Exception:
                pass
            raise RuntimeError(
                f"Telegram API error {response.status_code}: {description}"
            )

        if event_key:
            with self._lock:
                self._last_sent[event_key] = now
        return True

    def safe_send(self, text: str, **kwargs: Any) -> bool:
        """Send automatic alerts only when a fresh BUY_CANDIDATE appears.

        Manual `/api/telegram/test` uses `send()` directly and therefore still works.
        All routine engine/risk/fill/error summaries keep being journaled in the dashboard,
        but they no longer create Telegram noise.
        """
        event_key = str(kwargs.get("event_key") or "")
        if not (event_key.startswith("action-") and event_key.endswith("-BUY_CANDIDATE")):
            return False
        try:
            return self.send(text, **kwargs)
        except Exception:
            return False
