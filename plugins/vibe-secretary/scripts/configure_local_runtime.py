"""Pin the local plugin runtime to the repository virtual environment."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PLUGIN_ROOT.parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "src"))

from vibe_secretary.local_runtime import (  # noqa: E402
    LocalRuntimeConfigurationError,
    configure_local_runtime,
)


def main() -> int:
    try:
        result = configure_local_runtime(REPOSITORY_ROOT, Path(sys.executable))
    except LocalRuntimeConfigurationError as error:
        print(f"Local runtime configuration failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())