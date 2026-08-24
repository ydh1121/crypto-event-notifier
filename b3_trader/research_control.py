from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

CONTROL_PATH = Path("b3_trader/data/research-platform/components.json")
STATUS_PATH = Path("b3_trader/data/research-platform/status.json")
REFERENCE_STATE_PATH = Path("b3_trader/data/research-platform/reference-components-state.json")

COMPONENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "warehouse-export": {
        "label": "AI 분석 데이터 저장",
        "description": "가상매매·시장 기억 데이터를 Parquet 분석 창고에 추가 저장합니다.",
        "default_enabled": True,
        "default_interval_seconds": 300,
        "min_interval_seconds": 60,
    },
    "reference-version-watch": {
        "label": "외부 레포 버전 확인",
        "description": "참고 GitHub 프로젝트의 새 버전만 확인합니다. 코드는 자동 적용하지 않습니다.",
        "default_enabled": True,
        "default_interval_seconds": 21600,
        "min_interval_seconds": 300,
    },
    "cloudflare-snapshot-publish": {
        "label": "웹 상태판 데이터 보내기",
        "description": "24시간 PC의 가상매매 결과를 Cloudflare Pages 조회용 스냅샷으로 보냅니다.",
        "default_enabled": False,
        "default_interval_seconds": 20,
        "min_interval_seconds": 10,
    },
    "cloudflare-market-detail-publish": {
        "label": "웹 코인 상세 데이터 보내기",
        "description": "코인별 체결·매매계획·학습·자산곡선을 작게 나눠 Cloudflare 조회판으로 보냅니다.",
        "default_enabled": True,
        "default_interval_seconds": 30,
        "min_interval_seconds": 20,
    },
    "cloudflare-pages-deploy": {
        "label": "웹 화면 자동 배포",
        "description": "GitHub에서 새 웹 화면을 받은 뒤 Pages 코드가 바뀐 경우에만 pages.dev로 자동 배포합니다.",
        "default_enabled": False,
        "default_interval_seconds": 30,
        "min_interval_seconds": 15,
    },
}

_LOCK = threading.RLock()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def default_control() -> dict[str, Any]:
    return {
        "version": 2,
        "revision": 1,
        "enabled": True,
        "updated_at": time.time(),
        "components": {
            name: {
                "enabled": bool(definition.get("default_enabled", True)),
                "interval_seconds": float(definition["default_interval_seconds"]),
                "run_nonce": 0,
            }
            for name, definition in COMPONENT_DEFINITIONS.items()
        },
    }


def load_control(path: Path = CONTROL_PATH) -> dict[str, Any]:
    with _LOCK:
        loaded = _read_json(path)
        value = default_control()
        if loaded:
            value["version"] = max(2, int(loaded.get("version") or 2))
            value["revision"] = max(1, int(loaded.get("revision") or 1))
            value["enabled"] = bool(loaded.get("enabled", True))
            value["updated_at"] = float(loaded.get("updated_at") or value["updated_at"])
            source_components = loaded.get("components") if isinstance(loaded.get("components"), dict) else {}
            for name, definition in COMPONENT_DEFINITIONS.items():
                source = source_components.get(name) if isinstance(source_components.get(name), dict) else {}
                minimum = float(definition["min_interval_seconds"])
                interval = max(minimum, float(source.get("interval_seconds") or definition["default_interval_seconds"]))
                default_enabled = bool(definition.get("default_enabled", True))
                value["components"][name] = {
                    "enabled": bool(source.get("enabled", default_enabled)),
                    "interval_seconds": interval,
                    "run_nonce": max(0, int(source.get("run_nonce") or 0)),
                }
        if not path.exists():
            atomic_json(path, value)
        return value


def patch_component(
    name: str,
    *,
    enabled: bool | None = None,
    interval_seconds: float | None = None,
    run_now: bool = False,
    path: Path = CONTROL_PATH,
) -> dict[str, Any]:
    if name not in COMPONENT_DEFINITIONS:
        raise KeyError(name)
    with _LOCK:
        control = load_control(path)
        component = control["components"][name]
        if enabled is not None:
            component["enabled"] = bool(enabled)
        if interval_seconds is not None:
            minimum = float(COMPONENT_DEFINITIONS[name]["min_interval_seconds"])
            component["interval_seconds"] = max(minimum, float(interval_seconds))
        if run_now:
            component["run_nonce"] = int(component.get("run_nonce") or 0) + 1
        control["revision"] = int(control.get("revision") or 1) + 1
        control["updated_at"] = time.time()
        atomic_json(path, control)
        return control


def platform_snapshot(
    *,
    control_path: Path = CONTROL_PATH,
    status_path: Path = STATUS_PATH,
    reference_state_path: Path = REFERENCE_STATE_PATH,
) -> dict[str, Any]:
    control = load_control(control_path)
    status = _read_json(status_path)
    reference_state = _read_json(reference_state_path)
    now = time.time()
    status_updated_at = float(status.get("updated_at") or 0.0)
    supervisor_fresh = bool(status.get("running")) and status_updated_at > 0 and now - status_updated_at <= 15.0

    reference_rows = reference_state.get("components") if isinstance(reference_state.get("components"), list) else []
    reference_summary = {
        "checked_at": float(reference_state.get("checked_at") or 0.0),
        "total": len(reference_rows),
        "updates": sum(1 for row in reference_rows if isinstance(row, dict) and row.get("status") == "update_available"),
        "failed": sum(1 for row in reference_rows if isinstance(row, dict) and row.get("status") == "check_failed"),
        "auto_promote": False,
    }

    components: list[dict[str, Any]] = []
    status_components = status.get("components") if isinstance(status.get("components"), dict) else {}
    for name, definition in COMPONENT_DEFINITIONS.items():
        desired = control["components"].get(name) or {}
        runtime = status_components.get(name) if isinstance(status_components.get(name), dict) else {}
        components.append(
            {
                "name": name,
                "label": definition["label"],
                "description": definition["description"],
                "enabled": bool(desired.get("enabled", definition.get("default_enabled", True))) and bool(control.get("enabled", True)),
                "interval_seconds": float(desired.get("interval_seconds") or definition["default_interval_seconds"]),
                "run_nonce": int(desired.get("run_nonce") or 0),
                "status": runtime.get("status") or ("starting" if supervisor_fresh else "offline"),
                "last_started_at": float(runtime.get("last_started_at") or 0.0),
                "last_finished_at": float(runtime.get("last_finished_at") or 0.0),
                "last_success_at": float(runtime.get("last_success_at") or 0.0),
                "last_error_at": float(runtime.get("last_error_at") or 0.0),
                "last_error": str(runtime.get("last_error") or ""),
                "runs": int(runtime.get("runs") or 0),
                "last_result": runtime.get("last_result") if isinstance(runtime.get("last_result"), dict) else {},
            }
        )

    return {
        "version": 1,
        "paper_only": True,
        "supervisor_running": supervisor_fresh,
        "supervisor_pid": int(status.get("pid") or 0),
        "supervisor_started_at": float(status.get("started_at") or 0.0),
        "updated_at": status_updated_at,
        "control_revision": int(control.get("revision") or 1),
        "components": components,
        "references": reference_summary,
        "safety": {
            "can_place_orders": False,
            "can_modify_strategy_profiles": False,
            "auto_promote_external_code": False,
        },
    }
