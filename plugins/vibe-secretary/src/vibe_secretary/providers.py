"""Reserved provider boundary; Stage 4 implements Codex Host only."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ProviderMode(StrEnum):
    """Supported provider selection modes."""

    CODEX_HOST = "codex_host"
    BYOK = "byok"


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Non-secret provider configuration stored in project config."""

    mode: ProviderMode = ProviderMode.CODEX_HOST
    name: str = ""
    api_key_env: str = ""


class LLMProvider(Protocol):
    """Reserved BYOK provider seam; no implementation or network calls exist yet."""

    async def generate(self, *, instructions: str, input_text: str) -> str:
        """Generate text for a future business module."""
