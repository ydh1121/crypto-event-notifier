from __future__ import annotations

import time
from typing import Any

import requests

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
NON_RETRYABLE_ERROR_CODES = {"D1_WRITE_LIMIT", "D1_STORAGE_LIMIT"}


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    if response is not None:
        raw = response.headers.get("Retry-After", "").strip()
        if raw:
            try:
                return max(0.25, min(10.0, float(raw)))
            except ValueError:
                pass
    return min(8.0, 0.75 * (2 ** attempt))


def _response_error(response: requests.Response, url: str) -> requests.HTTPError:
    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error_payload = payload.get("error")
            if isinstance(error_payload, dict):
                code = str(error_payload.get("code") or "").strip()
                message = str(error_payload.get("message") or "").strip()
                if code or message:
                    detail = f" [{code}: {message}]" if code else f" [{message}]"
    except ValueError:
        text = str(response.text or "").strip().replace("\r", " ").replace("\n", " ")
        if text:
            detail = f" [{text[:240]}]"
    return requests.HTTPError(
        f"{response.status_code} Server Error for url: {url}{detail}",
        response=response,
    )


def _error_code(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    error_payload = payload.get("error")
    if not isinstance(error_payload, dict):
        return ""
    return str(error_payload.get("code") or "").strip().upper()


def get_with_retry(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 12.0,
    attempts: int = 3,
) -> tuple[requests.Response, int]:
    """GET with bounded retry for transient public-source/network failures."""
    last_error: Exception | None = None
    max_attempts = max(1, int(attempts))
    for attempt in range(max_attempts):
        response: requests.Response | None = None
        try:
            response = requests.get(url, headers=headers or {}, params=params, timeout=timeout)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response, attempt
            last_error = _response_error(response, response.url)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
        except requests.HTTPError:
            raise
        if attempt >= max_attempts - 1:
            break
        time.sleep(_retry_delay(response, attempt))
    if last_error is not None:
        raise last_error
    raise RuntimeError("HTTP GET failed without a response")


def post_with_retry(
    url: str,
    *,
    data: bytes,
    headers: dict[str, str],
    timeout: float,
    attempts: int = 3,
) -> tuple[requests.Response, int]:
    """POST with bounded retry for transient Cloudflare/network failures.

    Authentication/validation errors are intentionally not retried. Structured
    quota/storage errors are also terminal until their underlying condition is
    cleared, so retrying them only creates noise and unnecessary requests.
    """
    last_error: Exception | None = None
    max_attempts = max(1, int(attempts))
    for attempt in range(max_attempts):
        response: requests.Response | None = None
        try:
            response = requests.post(url, data=data, headers=headers, timeout=timeout)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response, attempt
            http_error = _response_error(response, url)
            if _error_code(response) in NON_RETRYABLE_ERROR_CODES:
                raise http_error
            last_error = http_error
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
        except requests.HTTPError:
            raise

        if attempt >= max_attempts - 1:
            break
        time.sleep(_retry_delay(response, attempt))

    if last_error is not None:
        raise last_error
    raise RuntimeError("Cloudflare POST failed without a response")
