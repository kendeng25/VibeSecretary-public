"""Privacy-preserving hook audit logging."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_audit_event(event: dict[str, Any]) -> None:
    """Append non-content hook metadata when Plugin data storage is available."""

    data_root = os.environ.get("PLUGIN_DATA")
    if not data_root:
        return
    try:
        root = Path(data_root).expanduser().resolve(strict=False)
        root.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": str(event.get("event", "unknown")),
            "tool": str(event.get("tool", "")),
            "decision": str(event.get("decision", "")),
            "reason": str(event.get("reason", "")),
            "mode": str(event.get("mode", "")),
            "source_count": int(event.get("source_count", 0)) if isinstance(event.get("source_count", 0), int) else 0,
        }
        with (root / "foundation-audit.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=True) + "\n")
    except OSError:
        return
