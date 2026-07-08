from __future__ import annotations

from typing import Any

SENSITIVE_KEY_PARTS = (
    "secret",
    "token",
    "email",
    "storage_key",
    "storagekey",
    "signed_url",
    "signedurl",
    "provider_url",
    "providerurl",
    "provider_payload",
    "providerpayload",
    "password",
    "credential",
)


def redact_sensitive(value: Any) -> Any:
    """Return a copy with sensitive fields removed/redacted for logs and events."""
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            normalized = key.replace("-", "_").lower()
            if any(part in normalized for part in SENSITIVE_KEY_PARTS):
                clean[key] = "[REDACTED]"
            else:
                clean[key] = redact_sensitive(item)
        return clean
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value
