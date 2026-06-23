from pathlib import Path


DEFAULT_PATCH_PATH = Path(".aidc") / "agent_patch.diff"
DEFAULT_PATCH_METADATA_PATH = Path(".aidc") / "agent_patch.json"


def resolve_patch_path(root=".", configured_path=None) -> Path:
    root_path = Path(root)

    if configured_path is None:
        return root_path / DEFAULT_PATCH_PATH

    patch_path = Path(configured_path)
    if patch_path.is_absolute():
        return patch_path

    return root_path / patch_path


def resolve_patch_metadata_path(root=".", configured_path=None) -> Path:
    root_path = Path(root)

    if configured_path is None:
        return root_path / DEFAULT_PATCH_METADATA_PATH

    metadata_path = Path(configured_path)
    if metadata_path.is_absolute():
        return metadata_path

    return root_path / metadata_path


def inspect_patch(root=".", configured_path=None) -> dict:
    patch_path = resolve_patch_path(root=root, configured_path=configured_path)
    display_path = _display_patch_path(configured_path)

    exists = patch_path.is_file()
    size = patch_path.stat().st_size if exists else 0

    if not exists:
        return {
            "status": "missing",
            "patch_path": display_path,
            "exists": False,
            "size": 0,
            "message": "Patch file not found.",
        }

    if size == 0:
        return {
            "status": "empty",
            "patch_path": display_path,
            "exists": True,
            "size": 0,
            "message": "Patch file is empty.",
        }

    return {
        "status": "ready",
        "patch_path": display_path,
        "exists": True,
        "size": size,
        "message": "Patch file is ready for review.",
    }


def build_patch_summary(root=".", configured_path=None) -> dict:
    return inspect_patch(root=root, configured_path=configured_path)


def read_patch_text(root=".", configured_path=None, max_bytes=262144) -> str:
    patch_path = resolve_patch_path(root=root, configured_path=configured_path)

    if max_bytes <= 0 or not patch_path.is_file():
        return ""

    with patch_path.open("rb") as handle:
        data = handle.read(max_bytes)

    if not data:
        return ""

    return data.decode("utf-8", errors="replace")


def _display_patch_path(configured_path) -> str:
    if configured_path is None:
        return str(DEFAULT_PATCH_PATH)

    return str(Path(configured_path))
