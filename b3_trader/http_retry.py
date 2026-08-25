from __future__ import annotations

import time
from typing import Any

import requests

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    if response is not None:
        raw = response.headers.get("Retry-After", "").strip()
        if raw:
            try:
                return max(0.25, min(10.0, float(raw)))
            except ValueError:
                pass
    return min(8.0, 0.75 * (2 ** attempt))


def post_with_retry(
    url: str,
    *,
    data: bytes,
    headers: dict[str, str],
    timeout: float,
    attempts: int = 3,
) -> tuple[requests.Response, int]:
    """POST with bounded retry for transient Cloudflare/network failures.

    Authentication/validation errors are intentionally not retried. The return
    value contains the successful response plus the number of retries used.
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
            last_error = requests.HTTPError(
                f"{response.status_code} Server Error for url: {url}", response=response
            )
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
