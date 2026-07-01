from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def is_absolute_path_string(path: str | Path) -> bool:
    raw_path = str(path)
    return raw_path.startswith(("/", "\\")) or bool(_WINDOWS_ABSOLUTE_PATH.match(raw_path))


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
