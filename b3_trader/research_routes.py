from __future__ import annotations

from typing import Any, Callable

from fastapi import Body, Depends, FastAPI, HTTPException, Request

from .research_control import COMPONENT_DEFINITIONS, patch_component, platform_snapshot

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


def install_research_routes(
    app: FastAPI,
    *,
    auth: Callable[..., None],
    require_loopback: Callable[[Request], None],
    journal: Any,
) -> None:
    @app.get("/api/research/components", dependencies=[Depends(auth)])
    def research_components(request: Request) -> dict[str, Any]:
        payload = platform_snapshot()
        client_host = request.client.host if request.client else ""
        payload["can_control"] = client_host in LOOPBACK_HOSTS
        payload["control_scope"] = "local_pc_only"
        return payload

    @app.patch("/api/research/components/{name}", dependencies=[Depends(auth)])
    def patch_research_component(
        name: str,
        request: Request,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        require_loopback(request)
        if name not in COMPONENT_DEFINITIONS:
            raise HTTPException(status_code=404, detail="research component not found")
        enabled = payload.get("enabled") if "enabled" in payload else None
        interval = payload.get("interval_seconds") if "interval_seconds" in payload else None
        try:
            patch_component(
                name,
                enabled=bool(enabled) if enabled is not None else None,
                interval_seconds=float(interval) if interval is not None else None,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="invalid research component settings") from exc
        journal.record_event(
            "research_component_updated",
            {"component": name, "enabled": enabled, "interval_seconds": interval, "local_only": True},
        )
        result = platform_snapshot()
        result["can_control"] = True
        result["control_scope"] = "local_pc_only"
        return result

    @app.post("/api/research/components/{name}/run", dependencies=[Depends(auth)])
    def run_research_component(name: str, request: Request) -> dict[str, Any]:
        require_loopback(request)
        if name not in COMPONENT_DEFINITIONS:
            raise HTTPException(status_code=404, detail="research component not found")
        current = platform_snapshot()
        component = next((row for row in current.get("components", []) if row.get("name") == name), None)
        if component and not component.get("enabled"):
            raise HTTPException(status_code=409, detail="enable the component before running it")
        patch_component(name, run_now=True)
        journal.record_event("research_component_run_requested", {"component": name, "local_only": True})
        result = platform_snapshot()
        result["can_control"] = True
        result["control_scope"] = "local_pc_only"
        return result
