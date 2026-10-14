"""Checksum-verified public response reuse without sharing session state."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CachedResponse:
    content: bytes
    raw_sha256: str
    scope: str
    validators: dict[str, str]


class PublicResponseCache:
    def __init__(self, session_dir: Path, shared_dir: Path | None, ttl_seconds: int) -> None:
        self.session_dir = session_dir
        self.shared_dir = shared_dir
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def request_key(
        provider: str,
        method: str,
        path: str,
        params: dict[str, Any],
        accept: str,
        body_sha256: str | None = None,
    ) -> str:
        wire = {
            "provider": provider,
            "method": method.upper(),
            "path": path,
            "params": params,
            "accept": accept,
            "body_sha256": body_sha256,
        }
        return hashlib.sha256(
            json.dumps(wire, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def get(self, request_key: str) -> CachedResponse | None:
        session_hit = self._read(self.session_dir, request_key)
        if session_hit is not None:
            content, raw_hash, validators = session_hit
            return CachedResponse(content, raw_hash, "reused_session", validators)
        if self.shared_dir is None:
            return None
        shared_hit = self._read(
            self.shared_dir,
            request_key,
            max_age_seconds=self.ttl_seconds,
        )
        if shared_hit is None:
            return None
        content, raw_hash, validators = shared_hit
        self._write(self.session_dir, request_key, content, raw_hash, validators)
        return CachedResponse(content, raw_hash, scope="reused_shared", validators=validators)

    def get_stale_shared(self, request_key: str) -> CachedResponse | None:
        """Return a checksum-verified shared response regardless of age.

        Callers may only reuse this value after a provider explicitly returns 304.
        It is intentionally not copied into the session until then.
        """
        if self.shared_dir is None:
            return None
        hit = self._read(self.shared_dir, request_key)
        if hit is None:
            return None
        content, raw_hash, validators = hit
        return CachedResponse(content, raw_hash, "stale_shared", validators)

    def put(
        self,
        request_key: str,
        content: bytes,
        validators: dict[str, str] | None = None,
    ) -> CachedResponse:
        raw_hash = hashlib.sha256(content).hexdigest()
        safe_validators = self._safe_validators(validators or {})
        self._write(self.session_dir, request_key, content, raw_hash, safe_validators)
        if self.shared_dir is not None:
            self._write(self.shared_dir, request_key, content, raw_hash, safe_validators)
        return CachedResponse(content, raw_hash, scope="completed", validators=safe_validators)

    @staticmethod
    def _read(
        directory: Path,
        request_key: str,
        max_age_seconds: int | None = None,
    ) -> tuple[bytes, str, dict[str, str]] | None:
        manifest_path = directory / "requests" / f"{request_key}.json"
        try:
            if max_age_seconds is not None and (
                time.time() - manifest_path.stat().st_mtime > max_age_seconds
            ):
                return None
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw_hash = str(manifest["raw_sha256"])
            if not re.fullmatch(r"[0-9a-f]{64}", raw_hash):
                return None
            content = (directory / f"{raw_hash}.raw").read_bytes()
            if hashlib.sha256(content).hexdigest() != raw_hash:
                return None
            validators = PublicResponseCache._safe_validators(manifest.get("validators", {}))
            return content, raw_hash, validators
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            return None

    @classmethod
    def _write(
        cls,
        directory: Path,
        request_key: str,
        content: bytes,
        raw_hash: str,
        validators: dict[str, str] | None = None,
    ) -> None:
        request_dir = directory / "requests"
        request_dir.mkdir(parents=True, exist_ok=True)
        cls._atomic_write(directory / f"{raw_hash}.raw", content)
        cls._atomic_write(
            request_dir / f"{request_key}.json",
            json.dumps(
                {"raw_sha256": raw_hash, "validators": validators or {}}, sort_keys=True
            ).encode(),
        )

    @staticmethod
    def _safe_validators(candidate: Any) -> dict[str, str]:
        if not isinstance(candidate, dict):
            return {}
        allowed = {"etag", "last-modified"}
        return {
            str(key).lower(): str(value)[:512]
            for key, value in candidate.items()
            if str(key).lower() in allowed and isinstance(value, str) and value
        }

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)
