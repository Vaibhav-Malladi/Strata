from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_text(path: str | Path, content: str, *, encoding: str = "utf-8") -> None:
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = target_path.with_name(f"{target_path.stem}.tmp{target_path.suffix}")
    temp_path.write_text(content, encoding=encoding)
    os.replace(temp_path, target_path)


def atomic_write_json(path: str | Path, payload: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
