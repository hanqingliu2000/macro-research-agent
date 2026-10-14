"""Shared bounded HTTP transport for public, cacheable connector requests."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from macro_research_agent.connectors.cache import PublicResponseCache
from macro_research_agent.connectors.rate_limit import PersistentRateLimiter, ProviderRateLimitError


class ConnectorHttpError(ValueError):
    pass


async def cached_public_get(
    *,
    provider: str,
    member: str,
    base_url: str,
    path: str,
    params: dict[str, Any],
    accept: str,
    media_tokens: tuple[str, ...],
    cache: PublicResponseCache,
    attempts: list[dict[str, Any]],
    max_bytes: int,
    client: httpx.AsyncClient | None = None,
    rate_limiter: PersistentRateLimiter | None = None,
) -> tuple[bytes, str]:
    """GET one allowlisted provider resource with bounded retries and conditional reuse."""
    request_key = cache.request_key(provider, "GET", path, params, accept)
    cached = cache.get(request_key)
    if cached is not None:
        attempts.append(
            {
                "member": member,
                "attempt": 0,
                "status": cached.scope,
                "raw_sha256": cached.raw_sha256,
            }
        )
        return cached.content, cached.raw_sha256

    stale = cache.get_stale_shared(request_key)
    conditional_headers: dict[str, str] = {}
    if stale is not None:
        if stale.validators.get("etag"):
            conditional_headers["If-None-Match"] = stale.validators["etag"]
        elif stale.validators.get("last-modified"):
            conditional_headers["If-Modified-Since"] = stale.validators["last-modified"]

    async def read(active_client: httpx.AsyncClient) -> tuple[bytes, dict[str, str]]:
        for attempt in range(3):
            try:
                if rate_limiter is not None:
                    rate_limiter.acquire()
                async with active_client.stream(
                    "GET",
                    f"{base_url.rstrip('/')}/{path.lstrip('/')}",
                    params=params,
                    headers={
                        "Accept": accept,
                        "Accept-Encoding": "identity",
                        **conditional_headers,
                    },
                    follow_redirects=False,
                    timeout=httpx.Timeout(connect=10, read=90, write=10, pool=10),
                ) as response:
                    if response.status_code == 304:
                        if stale is None or not conditional_headers:
                            raise ConnectorHttpError(
                                f"{provider} returned 304 without a validated cached response."
                            )
                        validators = {
                            key.lower(): value
                            for key, value in response.headers.items()
                            if key.lower() in {"etag", "last-modified"}
                        } or stale.validators
                        cache.put(request_key, stale.content, validators)
                        attempts.append(
                            {
                                "member": member,
                                "attempt": attempt + 1,
                                "status": "not_modified",
                                "raw_sha256": stale.raw_sha256,
                            }
                        )
                        return stale.content, validators
                    retryable = response.status_code == 429 or response.status_code in {
                        500,
                        502,
                        503,
                        504,
                    }
                    if retryable and attempt < 2:
                        attempts.append(
                            {"member": member, "attempt": attempt + 1, "status": "retryable"}
                        )
                        retry_after = response.headers.get("Retry-After", "1")
                        delay = (
                            min(float(retry_after), 5.0)
                            if retry_after.isdigit()
                            else float(attempt + 1)
                        )
                        await asyncio.sleep(delay)
                        continue
                    if response.status_code != 200:
                        attempts.append(
                            {"member": member, "attempt": attempt + 1, "status": "failed"}
                        )
                        meaning = "no matching data" if response.status_code == 404 else "failed"
                        raise ConnectorHttpError(
                            f"{provider} request {meaning} (HTTP {response.status_code})."
                        )
                    media = response.headers.get("content-type", "").lower()
                    if not any(token in media for token in media_tokens):
                        raise ConnectorHttpError(f"{provider} returned an unexpected media type.")
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > max_bytes:
                            raise ConnectorHttpError(
                                f"{provider} response exceeds the {max_bytes} byte limit."
                            )
                    validators = {
                        key.lower(): value
                        for key, value in response.headers.items()
                        if key.lower() in {"etag", "last-modified"}
                    }
                    return bytes(chunks), validators
            except ProviderRateLimitError as error:
                attempts.append(
                    {"member": member, "attempt": attempt + 1, "status": "rate_limited"}
                )
                raise ConnectorHttpError(str(error)) from error
            except httpx.TransportError as error:
                attempts.append(
                    {
                        "member": member,
                        "attempt": attempt + 1,
                        "status": "retryable" if attempt < 2 else "failed",
                    }
                )
                if attempt < 2:
                    await asyncio.sleep(float(attempt + 1))
                    continue
                raise ConnectorHttpError(f"{provider} connection failed; retry later.") from error
        raise ConnectorHttpError(f"{provider} request failed.")

    if client is not None:
        raw, validators = await read(client)
    else:
        async with httpx.AsyncClient() as active_client:
            raw, validators = await read(active_client)
    stored = cache.put(request_key, raw, validators)
    if not attempts or attempts[-1].get("status") != "not_modified":
        attempts.append(
            {
                "member": member,
                "attempt": 1,
                "status": "completed",
                "raw_sha256": stored.raw_sha256,
            }
        )
    return raw, stored.raw_sha256
