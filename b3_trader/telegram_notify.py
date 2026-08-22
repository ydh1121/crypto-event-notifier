from __future__ import annotations

import threading
import time
from typing import Any

import requests


class TelegramNotifier:
    def __init__(self, token: str = "", chat_id: str = "", *, enabled: bool = False, timeout: float = 5.0) -> None:
        self.token = token.strip()
        self.chat_id = chat_id.strip()
        self.enabled = bool(enabled and self.token and self.chat_id)
        self.timeout = timeout
        self.session = requests.Session()
        self._lock = threading.Lock()
        self._last_sent: dict[str, float] = {}

    def send(self, text: str, *, event_key: str = "", min_interval_seconds: float = 0.0, disable_notification: bool = False) -> bool:
        if not self.enabled:
            return False
        now = time.time()
        if event_key:
            with self._lock:
                last = self._last_sent.get(event_key, 0.0)
                if now - last < min_interval_seconds:
                    return False
        response = self.session.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            data={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": "true",
                "disable_notification": "true" if disable_notification else "false",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        if event_key:
            with self._lock:
                self._last_sent[event_key] = now
        return True

    def safe_send(self, text: str, **kwargs: Any) -> bool:
        try:
            return self.send(text, **kwargs)
        except Exception:
            return False
