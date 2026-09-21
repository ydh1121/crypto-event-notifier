from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class TelegramSettings:
    enabled: bool = False
    token: str = ""
    chat_id: str = ""

    def public_dict(self) -> dict:
        return {
            "enabled": bool(self.enabled and self.token and self.chat_id),
            "configured": bool(self.token and self.chat_id),
            "token_configured": bool(self.token),
            "chat_id": self.chat_id,
        }


class TelegramSettingsStore:
    def __init__(
        self,
        path: str = "b3_trader/data/telegram-config.json",
        *,
        default_enabled: bool = False,
        default_token: str = "",
        default_chat_id: str = "",
    ) -> None:
        self.path = Path(path)
        self.defaults = TelegramSettings(
            enabled=default_enabled,
            token=default_token.strip(),
            chat_id=default_chat_id.strip(),
        )

    def load(self) -> TelegramSettings:
        if not self.path.exists():
            return TelegramSettings(**asdict(self.defaults))
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return TelegramSettings(
                enabled=bool(payload.get("enabled", False)),
                token=str(payload.get("token") or "").strip(),
                chat_id=str(payload.get("chat_id") or "").strip(),
            )
        except Exception:
            return TelegramSettings(**asdict(self.defaults))

    def save(self, settings: TelegramSettings) -> TelegramSettings:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)
        return settings

    def patch(
        self,
        *,
        enabled: bool | None = None,
        token: str | None = None,
        chat_id: str | None = None,
    ) -> TelegramSettings:
        current = self.load()
        if enabled is not None:
            current.enabled = bool(enabled)
        if token is not None and token.strip():
            current.token = token.strip()
        if chat_id is not None and chat_id.strip():
            current.chat_id = chat_id.strip()
        return self.save(current)
