from dataclasses import dataclass
from typing import Iterable

from strata.core.candidates import normalize_task_tokens, score_candidate
from strata.core.frontend_roles import infer_frontend_role_from_path
from strata.core.inventory import InventoryRecord, is_generated_path


DEFAULT_REACT_STARTING_FILE_LIMIT = 20

_REACT_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}
_REACT_PATH_HINTS = {
    "api",
    "app",
    "client",
    "clients",
    "component",
    "components",
    "form",
    "forms",
    "hook",
    "hooks",
    "page",
    "pages",
    "route",
    "router",
    "routes",
    "store",
    "stores",
}
_TEST_TASK_WORDS = {"spec", "specs", "test", "testing", "tests"}
_ROLE_BASE_SCORES = {
    "page": 4,
    "component": 3,
    "form": 4,
    "hook": 2,
    "api_client": 2,
    "state_store": 2,
    "route": 2,
}
_ROLE_TASK_WORDS = {
    "page": {"page", "screen", "view"},
    "component": {"component"},
    "form": {"form", "forms"},
    "hook": {"hook", "hooks"},
    "api_client": {"api", "client"},
    "state_store": {"state", "store", "stores"},
    "route": {"route", "router", "routes", "routing"},
}
_UI_TASK_WORDS = {"button", "component", "form", "forms", "page", "ui", "view"}
_UI_STARTING_ROLES = {"component", "form", "page"}


@dataclass(frozen=True, slots=True)
class ReactStartingFile:
    path: str
    role: str
    score: int
    reasons: tuple[str, ...]
    confidence: str


def select_react_starting_files(
    records: Iterable[InventoryRecord],
    task: str,
    limit: int = DEFAULT_REACT_STARTING_FILE_LIMIT,
) -> tuple[ReactStartingFile, ...]:
    """Select bounded React starting files using path-derived signals only."""

    _validate_limit(limit)
    task_tokens = set(normalize_task_tokens(task))
    asks_for_tests = bool(task_tokens & _TEST_TASK_WORDS)
    starting_files: list[ReactStartingFile] = []

    for record in records:
        extension = _path_extension(record.path)
        if extension not in _REACT_EXTENSIONS:
            continue
        if (
            record.is_generated_guess
            or record.folder_role in {"generated", "vendor"}
            or is_generated_path(record.path)
        ):
            continue

        role = infer_frontend_role_from_path(record.path)
        is_test = record.is_test or role == "test"
        if is_test and not asks_for_tests:
            continue

        candidate = score_candidate(record, task)
        score = candidate.score
        reasons = list(candidate.reasons)

        extension_score = 2 if extension in {".jsx", ".tsx"} else 1
        score += extension_score
        reasons.append(f"React-like extension '{extension}' (+{extension_score})")

        role_score = _ROLE_BASE_SCORES.get(role, 0)
        if role_score:
            score += role_score
            reasons.append(f"React starting role '{role}' (+{role_score})")

        folder_names = _folder_names(record.path)
        path_hints = sorted(folder_names & _REACT_PATH_HINTS)
        if path_hints:
            score += 1
            reasons.append(f"React path hint '{path_hints[0]}' (+1)")

        role_task_words = _ROLE_TASK_WORDS.get(role, set())
        if task_tokens & role_task_words:
            score += 6
            reasons.append(f"React role '{role}' matches task (+6)")
        elif role in _UI_STARTING_ROLES and task_tokens & _UI_TASK_WORDS:
            score += 4
            reasons.append(f"React UI starting role '{role}' is relevant (+4)")

        starting_files.append(
            ReactStartingFile(
                path=record.path,
                role=role,
                score=score,
                reasons=tuple(reasons),
                confidence=_confidence(score),
            )
        )

    starting_files.sort(key=lambda item: (-item.score, item.path.lower(), item.path))
    return tuple(starting_files[:limit])


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")


def _path_extension(path: str) -> str:
    filename = str(path).replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in filename:
        return ""
    return f".{filename.rsplit('.', 1)[-1].lower()}"


def _folder_names(path: str) -> set[str]:
    normalized = str(path).replace("\\", "/")
    parts = [part.lower() for part in normalized.split("/") if part]
    return set(parts[:-1])


def _confidence(score: int) -> str:
    if score >= 16:
        return "high"
    if score >= 8:
        return "medium"
    return "low"
