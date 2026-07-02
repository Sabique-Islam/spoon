import asyncio
from typing import Any

import httpx

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_RETRIES = 3


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    timeout: float = 120.0,
    **kwargs: Any,
) -> httpx.Response:
    last_response: httpx.Response | None = None
    for attempt in range(MAX_RETRIES):
        response = await client.request(method, url, timeout=timeout, **kwargs)
        last_response = response
        if response.status_code not in RETRYABLE_STATUS:
            return response
        retry_after = int(response.headers.get("Retry-After", 2**attempt))
        await asyncio.sleep(retry_after)

    assert last_response is not None
    return last_response
