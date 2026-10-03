"""Stable error types and result envelopes for VibeSecretary APIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FoundationError(Exception):
    """An expected VibeSecretary failure safe to return to clients."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


def success(data: dict[str, Any]) -> dict[str, Any]:
    """Build a stable success envelope."""

    return {"ok": True, "data": data, "error": None}


def failure(error: FoundationError) -> dict[str, Any]:
    """Build a stable expected-error envelope."""

    return {"ok": False, "data": None, "error": error.to_dict()}


def internal_failure() -> dict[str, Any]:
    """Hide unexpected exception details from clients."""

    return {
        "ok": False,
        "data": None,
        "error": {
            "code": "internal_error",
            "message": "VibeSecretary encountered an unexpected error.",
            "details": {},
        },
    }
