from dataclasses import dataclass
from typing import Iterable

from strata.core.candidates import normalize_task_tokens, score_candidate
from strata.core.frontend_roles import infer_frontend_role_from_path
from strata.core.inventory import InventoryRecord, is_generated_path


DEFAULT_ANGULAR_STARTING_FILE_LIMIT = 20

_ANGULAR_EXTENSIONS = {".ts", ".html", ".css", ".scss", ".sass", ".less"}
_ANGULAR_PATH_HINTS = {
    "app",
    "component",
    "components",
    "feature",
    "features",
    "guard",
    "guards",
    "interceptor",
    "interceptors",
    "module",
    "modules",
    "page",
    "pages",
    "route",
    "routes",
    "routing",
    "service",
    "services",
    "shared",
}
_TEST_TASK_WORDS = {"spec", "specs", "test", "testing", "tests"}
_KIND_ROLES = {
    "component": "component",
    "template": "template",
    "style": "style",
    "service": "service",
    "guard": "service",
    "interceptor": "service",
    "route": "route",
    "module": "config",
    "pipe": "component",
    "directive": "component",
}
_ROLE_BASE_SCORES = {
    "template": 4,
    "component": 3,
    "style": 2,
    "service": 2,
    "route": 3,
    "config": 1,
}
_UI_TASK_WORDS = {"button", "component", "form", "forms", "html", "template", "ui"}
_SERVICE_TASK_WORDS = {"api", "auth", "client", "data", "service", "services"}
_ROUTE_TASK_WORDS = {"dashboard", "navigation", "page", "route", "routes", "routing"}
_STYLE_TASK_WORDS = {"css", "layout", "scss", "style", "styles"}


@dataclass(frozen=True, slots=True)
class AngularStartingFile:
    path: str
    role: str
    score: int
    reasons: tuple[str, ...]
    confidence: str


def select_angular_starting_files(
    records: Iterable[InventoryRecord],
    task: str,
    limit: int = DEFAULT_ANGULAR_STARTING_FILE_LIMIT,
) -> tuple[AngularStartingFile, ...]:
    """Select bounded Angular starting files using path-derived signals only."""

    _validate_limit(limit)
    task_tokens = set(normalize_task_tokens(task))
    asks_for_tests = bool(task_tokens & _TEST_TASK_WORDS)
    starting_files: list[AngularStartingFile] = []

    for record in records:
        extension = _path_extension(record.path)
        if extension not in _ANGULAR_EXTENSIONS:
            continue
        if (
            record.is_generated_guess
            or record.folder_role in {"generated", "vendor"}
            or is_generated_path(record.path)
        ):
            continue

        inferred_role = infer_frontend_role_from_path(record.path)
        is_test = record.is_test or inferred_role == "test"
        if is_test and not asks_for_tests:
            continue

        kind = _angular_kind(record.path, extension)
        role = "test" if is_test else _KIND_ROLES.get(kind, inferred_role)
        candidate = score_candidate(record, task)
        score = candidate.score
        reasons = list(candidate.reasons)

        score += 1
        reasons.append(f"Angular-like extension '{extension}' (+1)")

        if kind:
            score += 3
            reasons.append(f"Angular file pattern '{kind}' (+3)")

        role_score = _ROLE_BASE_SCORES.get(role, 0)
        if role_score:
            score += role_score
            reasons.append(f"Angular starting role '{role}' (+{role_score})")

        path_hints = sorted(_folder_names(record.path) & _ANGULAR_PATH_HINTS)
        if path_hints:
            score += 1
            reasons.append(f"Angular path hint '{path_hints[0]}' (+1)")

        task_score, task_reason = _task_preference(kind, role, task_tokens)
        if task_score:
            score += task_score
            reasons.append(f"{task_reason} (+{task_score})")

        starting_files.append(
            AngularStartingFile(
                path=record.path,
                role=role,
                score=score,
                reasons=tuple(reasons),
                confidence=_confidence(score),
            )
        )

    starting_files.sort(key=lambda item: (-item.score, item.path.lower(), item.path))
    return tuple(starting_files[:limit])


def _task_preference(
    kind: str,
    role: str,
    task_tokens: set[str],
) -> tuple[int, str]:
    if kind == "guard" and task_tokens & {"guard", "guards"}:
        return 7, "Angular guard matches task"
    if kind == "interceptor" and task_tokens & {"interceptor", "interceptors"}:
        return 7, "Angular interceptor matches task"
    if kind == "service" and task_tokens & _SERVICE_TASK_WORDS:
        return 6, "Angular service matches task"
    if role == "route" and task_tokens & _ROUTE_TASK_WORDS:
        return 6, "Angular route matches task"
    if role == "style" and task_tokens & _STYLE_TASK_WORDS:
        return 7, "Angular style matches task"
    if role in {"component", "template"} and task_tokens & _UI_TASK_WORDS:
        return 5, f"Angular UI starting role '{role}' is relevant"
    return 0, ""


def _angular_kind(path: str, extension: str) -> str:
    filename = str(path).replace("\\", "/").rsplit("/", 1)[-1].lower()
    if ".component." in filename:
        if extension == ".html":
            return "template"
        if extension in {".css", ".scss", ".sass", ".less"}:
            return "style"
        return "component"
    if ".service." in filename:
        return "service"
    if ".guard." in filename:
        return "guard"
    if ".interceptor." in filename:
        return "interceptor"
    if ".routes." in filename or "routing.module." in filename:
        return "route"
    if ".module." in filename:
        return "module"
    if ".pipe." in filename:
        return "pipe"
    if ".directive." in filename:
        return "directive"
    if extension == ".html":
        return "template"
    if extension in {".css", ".scss", ".sass", ".less"}:
        return "style"
    return ""


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
