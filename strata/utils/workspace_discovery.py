"""Bounded workspace repository discovery suggestions.

Q2 discovery is intentionally suggestive. It inspects only direct children of a
bounded search root, reads small known manifest/configuration files, and never
modifies `.aidc/config.json`.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import tomllib
from typing import Any

import strata.utils.workspace_config as workspace_config


WORKSPACE_DISCOVERY_SCHEMA_VERSION = 1

DEFAULT_MAX_CANDIDATES = 25
DEFAULT_MAX_EVIDENCE_PER_CANDIDATE = 8

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"
CONFIDENCE_LEVELS = (
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_HIGH,
)

EVIDENCE_STRENGTH_WEAK = "weak"
EVIDENCE_STRENGTH_MEDIUM = "medium"
EVIDENCE_STRENGTH_STRONG = "strong"
EVIDENCE_STRENGTHS = (
    EVIDENCE_STRENGTH_WEAK,
    EVIDENCE_STRENGTH_MEDIUM,
    EVIDENCE_STRENGTH_STRONG,
)

SIGNAL_SIBLING_PROXIMITY = "sibling_proximity"
SIGNAL_GIT_MARKER = "git_marker"
SIGNAL_PROJECT_MANIFEST = "project_manifest"
SIGNAL_LOCAL_PATH_REFERENCE = "local_path_reference"
SIGNAL_WORKSPACE_FILE_MEMBERSHIP = "workspace_file_membership"
SIGNAL_DOCKER_COMPOSE_BUILD_CONTEXT = "docker_compose_build_context"
SIGNAL_NAME_SIMILARITY = "name_similarity"
SIGNAL_TYPES = (
    SIGNAL_SIBLING_PROXIMITY,
    SIGNAL_GIT_MARKER,
    SIGNAL_PROJECT_MANIFEST,
    SIGNAL_LOCAL_PATH_REFERENCE,
    SIGNAL_WORKSPACE_FILE_MEMBERSHIP,
    SIGNAL_DOCKER_COMPOSE_BUILD_CONTEXT,
    SIGNAL_NAME_SIMILARITY,
)

DIAGNOSTIC_SEVERITY_INFO = "info"
DIAGNOSTIC_SEVERITY_WARNING = "warning"
DIAGNOSTIC_SEVERITY_ERROR = "error"
DIAGNOSTIC_SEVERITIES = (
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    DIAGNOSTIC_SEVERITY_ERROR,
)

DIAGNOSTIC_SEARCH_ROOT_MISSING = "workspace_discovery_search_root_missing"
DIAGNOSTIC_SEARCH_ROOT_UNREADABLE = "workspace_discovery_search_root_unreadable"
DIAGNOSTIC_SEARCH_ROOT_NOT_DIRECTORY = "workspace_discovery_search_root_not_directory"
DIAGNOSTIC_REPOSITORY_ROOT_MISSING = "workspace_discovery_repository_root_missing"
DIAGNOSTIC_REPOSITORY_ROOT_NOT_DIRECTORY = "workspace_discovery_repository_root_not_directory"
DIAGNOSTIC_REPOSITORY_OUTSIDE_SEARCH_ROOT = "workspace_discovery_repository_outside_search_root"
DIAGNOSTIC_CANDIDATE_UNREADABLE = "workspace_discovery_candidate_unreadable"
DIAGNOSTIC_MALFORMED_MANIFEST = "workspace_discovery_malformed_manifest"
DIAGNOSTIC_CANDIDATE_CAP_REACHED = "workspace_discovery_candidate_cap_reached"
DIAGNOSTIC_EVIDENCE_CAP_REACHED = "workspace_discovery_evidence_cap_reached"
DIAGNOSTIC_PATH_ESCAPED_SEARCH_BOUNDARY = "workspace_discovery_path_escaped_search_boundary"
DIAGNOSTIC_SYMLINK_SKIPPED = "workspace_discovery_symlink_skipped"
DIAGNOSTIC_DUPLICATE_CANDIDATE_PATH = "workspace_discovery_duplicate_candidate_path"
DIAGNOSTIC_UNSUPPORTED_OR_AMBIGUOUS_MANIFEST = "workspace_discovery_unsupported_or_ambiguous_manifest"
DIAGNOSTIC_CODES = (
    DIAGNOSTIC_SEARCH_ROOT_MISSING,
    DIAGNOSTIC_SEARCH_ROOT_UNREADABLE,
    DIAGNOSTIC_SEARCH_ROOT_NOT_DIRECTORY,
    DIAGNOSTIC_REPOSITORY_ROOT_MISSING,
    DIAGNOSTIC_REPOSITORY_ROOT_NOT_DIRECTORY,
    DIAGNOSTIC_REPOSITORY_OUTSIDE_SEARCH_ROOT,
    DIAGNOSTIC_CANDIDATE_UNREADABLE,
    DIAGNOSTIC_MALFORMED_MANIFEST,
    DIAGNOSTIC_CANDIDATE_CAP_REACHED,
    DIAGNOSTIC_EVIDENCE_CAP_REACHED,
    DIAGNOSTIC_PATH_ESCAPED_SEARCH_BOUNDARY,
    DIAGNOSTIC_SYMLINK_SKIPPED,
    DIAGNOSTIC_DUPLICATE_CANDIDATE_PATH,
    DIAGNOSTIC_UNSUPPORTED_OR_AMBIGUOUS_MANIFEST,
)

DISCOVERY_SOURCE_BOUNDED_SIBLING_SCAN = "bounded_sibling_scan"

IGNORED_DIRECTORY_NAMES = {
    ".aidc",
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "target",
    "vendor",
    "venv",
    ".codex-venv",
}

REPOSITORY_MARKERS = (
    ".git",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "angular.json",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
    "pnpm-workspace.yaml",
    "yarn.lock",
    "package-lock.json",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

MANIFEST_FILES = (
    "package.json",
    "pyproject.toml",
    "go.mod",
    "angular.json",
    "pnpm-workspace.yaml",
    "go.work",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

DOCKER_COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

PYTHON_BACKEND_DEPENDENCY_NAMES = {
    "django",
    "fastapi",
    "flask",
    "starlette",
}

FRONTEND_PACKAGE_NAMES = {
    "@angular/core",
    "react",
    "react-dom",
}

EVIDENCE_WEIGHTS = {
    SIGNAL_SIBLING_PROXIMITY: 0.10,
    SIGNAL_GIT_MARKER: 0.05,
    SIGNAL_PROJECT_MANIFEST: 0.15,
    SIGNAL_LOCAL_PATH_REFERENCE: 0.45,
    SIGNAL_WORKSPACE_FILE_MEMBERSHIP: 0.50,
    SIGNAL_DOCKER_COMPOSE_BUILD_CONTEXT: 0.45,
    SIGNAL_NAME_SIMILARITY: 0.10,
}

EVIDENCE_FIELD_ORDER = (
    "signal_type",
    "source_path",
    "summary",
    "strength",
    "referenced_path",
)
CANDIDATE_FIELD_ORDER = (
    "path",
    "suggested_id",
    "display_name",
    "probable_role",
    "confidence",
    "confidence_score",
    "evidence",
    "warnings",
    "discovery_source",
)
DIAGNOSTIC_FIELD_ORDER = (
    "code",
    "severity",
    "message",
    "path",
    "details",
)
DISCOVERY_RESULT_FIELD_ORDER = (
    "schema_version",
    "repository_root",
    "search_root",
    "candidates",
    "diagnostics",
)


def _validate_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{name} must not have surrounding whitespace")
    return value


def _validate_choice(value: Any, name: str, choices: tuple[str, ...]) -> str:
    text = _validate_nonempty_string(value, name)
    if text not in choices:
        raise ValueError(f"{name} must be one of: {', '.join(choices)}")
    return text


def _validate_optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _validate_nonempty_string(value, name)


def _validate_probability(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0.0 or normalized > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return round(normalized, 3)


def _validate_strings(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        items = tuple(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    return tuple(_validate_nonempty_string(item, f"{name}[{index}]") for index, item in enumerate(items))


def _copy_json_details(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        return value
    if isinstance(value, Mapping):
        copied = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise ValueError(f"{name} keys must be strings")
            copied[key] = _copy_json_details(value[key], f"{name}.{key}")
        return copied
    if isinstance(value, (list, tuple)):
        return [
            _copy_json_details(item, f"{name}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ValueError(f"{name} must be JSON-ready")


def _normalize_path_text(value: str | Path) -> str:
    text = str(value).replace("\\", "/")
    return PurePosixPath(text).as_posix()


def _is_ignored_directory_name(name: str) -> bool:
    normalized = name.strip().lower()
    if not normalized:
        return True
    return normalized in IGNORED_DIRECTORY_NAMES or normalized.endswith(".egg-info")


def _safe_resolve(path: Path) -> Path:
    return path.resolve(strict=False)


@dataclass(frozen=True, slots=True)
class WorkspaceDiscoveryEvidence:
    signal_type: str
    source_path: str
    summary: str
    strength: str
    referenced_path: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "signal_type",
            _validate_choice(self.signal_type, "signal_type", SIGNAL_TYPES),
        )
        object.__setattr__(
            self,
            "source_path",
            _validate_nonempty_string(self.source_path, "source_path"),
        )
        object.__setattr__(
            self,
            "summary",
            _validate_nonempty_string(self.summary, "summary"),
        )
        object.__setattr__(
            self,
            "strength",
            _validate_choice(self.strength, "strength", EVIDENCE_STRENGTHS),
        )
        object.__setattr__(
            self,
            "referenced_path",
            _validate_optional_string(self.referenced_path, "referenced_path"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "source_path": self.source_path,
            "summary": self.summary,
            "strength": self.strength,
            "referenced_path": self.referenced_path,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceDiscoveryDiagnostic:
    code: str
    severity: str
    message: str
    path: str | None = None
    details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "code",
            _validate_choice(self.code, "code", DIAGNOSTIC_CODES),
        )
        object.__setattr__(
            self,
            "severity",
            _validate_choice(self.severity, "severity", DIAGNOSTIC_SEVERITIES),
        )
        object.__setattr__(
            self,
            "message",
            _validate_nonempty_string(self.message, "message"),
        )
        object.__setattr__(
            self,
            "path",
            _validate_optional_string(self.path, "path"),
        )
        object.__setattr__(
            self,
            "details",
            _copy_json_details(self.details or {}, "details"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "details": dict(self.details or {}),
        }


@dataclass(frozen=True, slots=True)
class WorkspaceRepositorySuggestion:
    path: str
    suggested_id: str
    display_name: str
    probable_role: str
    confidence: str
    confidence_score: float
    evidence: tuple[WorkspaceDiscoveryEvidence, ...]
    warnings: tuple[str, ...] = ()
    discovery_source: str = DISCOVERY_SOURCE_BOUNDED_SIBLING_SCAN

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _validate_nonempty_string(self.path, "path"))
        object.__setattr__(
            self,
            "suggested_id",
            _validate_nonempty_string(self.suggested_id, "suggested_id"),
        )
        object.__setattr__(
            self,
            "display_name",
            _validate_nonempty_string(self.display_name, "display_name"),
        )
        object.__setattr__(
            self,
            "probable_role",
            _validate_choice(
                self.probable_role,
                "probable_role",
                workspace_config.REPOSITORY_ROLES,
            ),
        )
        object.__setattr__(
            self,
            "confidence",
            _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS),
        )
        object.__setattr__(
            self,
            "confidence_score",
            _validate_probability(self.confidence_score, "confidence_score"),
        )
        object.__setattr__(
            self,
            "evidence",
            tuple(_coerce_evidence(item) for item in self.evidence),
        )
        object.__setattr__(self, "warnings", _validate_strings(self.warnings, "warnings"))
        object.__setattr__(
            self,
            "discovery_source",
            _validate_nonempty_string(self.discovery_source, "discovery_source"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "suggested_id": self.suggested_id,
            "display_name": self.display_name,
            "probable_role": self.probable_role,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "evidence": [item.to_dict() for item in self.evidence],
            "warnings": list(self.warnings),
            "discovery_source": self.discovery_source,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceDiscoveryResult:
    repository_root: str
    search_root: str
    candidates: tuple[WorkspaceRepositorySuggestion, ...] = ()
    diagnostics: tuple[WorkspaceDiscoveryDiagnostic, ...] = ()
    schema_version: int = WORKSPACE_DISCOVERY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != WORKSPACE_DISCOVERY_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {WORKSPACE_DISCOVERY_SCHEMA_VERSION}"
            )
        object.__setattr__(
            self,
            "repository_root",
            _validate_nonempty_string(self.repository_root, "repository_root"),
        )
        object.__setattr__(
            self,
            "search_root",
            _validate_nonempty_string(self.search_root, "search_root"),
        )
        object.__setattr__(
            self,
            "candidates",
            tuple(sorted((_coerce_candidate(item) for item in self.candidates), key=_candidate_sort_key)),
        )
        object.__setattr__(
            self,
            "diagnostics",
            tuple(sorted((_coerce_diagnostic(item) for item in self.diagnostics), key=_diagnostic_sort_key)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repository_root": self.repository_root,
            "search_root": self.search_root,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class _ManifestInfo:
    markers: tuple[str, ...] = ()
    project_names: tuple[str, ...] = ()
    probable_role: str = workspace_config.REPOSITORY_ROLE_UNKNOWN
    diagnostics: tuple[WorkspaceDiscoveryDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class _CandidateAnalysis:
    root: Path
    resolved_root: Path
    relative_path: str
    suggested_id: str
    display_name: str
    probable_role: str
    evidence: tuple[WorkspaceDiscoveryEvidence, ...]
    diagnostics: tuple[WorkspaceDiscoveryDiagnostic, ...]


def _coerce_evidence(value: Any) -> WorkspaceDiscoveryEvidence:
    if isinstance(value, WorkspaceDiscoveryEvidence):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("evidence must be a WorkspaceDiscoveryEvidence or mapping")
    return WorkspaceDiscoveryEvidence(
        signal_type=value["signal_type"],
        source_path=value["source_path"],
        summary=value["summary"],
        strength=value["strength"],
        referenced_path=value.get("referenced_path"),
    )


def _coerce_diagnostic(value: Any) -> WorkspaceDiscoveryDiagnostic:
    if isinstance(value, WorkspaceDiscoveryDiagnostic):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("diagnostic must be a WorkspaceDiscoveryDiagnostic or mapping")
    return WorkspaceDiscoveryDiagnostic(
        code=value["code"],
        severity=value["severity"],
        message=value["message"],
        path=value.get("path"),
        details=value.get("details"),
    )


def _coerce_candidate(value: Any) -> WorkspaceRepositorySuggestion:
    if isinstance(value, WorkspaceRepositorySuggestion):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("candidate must be a WorkspaceRepositorySuggestion or mapping")
    return WorkspaceRepositorySuggestion(
        path=value["path"],
        suggested_id=value["suggested_id"],
        display_name=value["display_name"],
        probable_role=value["probable_role"],
        confidence=value["confidence"],
        confidence_score=value["confidence_score"],
        evidence=tuple(value["evidence"]),
        warnings=tuple(value.get("warnings", ())),
        discovery_source=value.get("discovery_source", DISCOVERY_SOURCE_BOUNDED_SIBLING_SCAN),
    )


def _candidate_sort_key(candidate: WorkspaceRepositorySuggestion) -> tuple[object, ...]:
    return (
        -candidate.confidence_score,
        candidate.path,
        candidate.suggested_id,
    )


def _diagnostic_sort_key(diagnostic: WorkspaceDiscoveryDiagnostic) -> tuple[object, ...]:
    return (
        diagnostic.code,
        diagnostic.path or "",
        diagnostic.message,
        json.dumps(diagnostic.details or {}, sort_keys=True),
    )


def _evidence_sort_key(evidence: WorkspaceDiscoveryEvidence) -> tuple[object, ...]:
    return (
        _signal_priority(evidence.signal_type),
        evidence.source_path,
        evidence.referenced_path or "",
        evidence.summary,
    )


def _signal_priority(signal_type: str) -> int:
    return SIGNAL_TYPES.index(signal_type)


def _diagnostic(
    code: str,
    severity: str,
    message: str,
    *,
    path: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> WorkspaceDiscoveryDiagnostic:
    return WorkspaceDiscoveryDiagnostic(
        code=code,
        severity=severity,
        message=message,
        path=path,
        details=details,
    )


def _evidence(
    signal_type: str,
    source_path: str,
    summary: str,
    strength: str,
    *,
    referenced_path: str | None = None,
) -> WorkspaceDiscoveryEvidence:
    return WorkspaceDiscoveryEvidence(
        signal_type=signal_type,
        source_path=source_path,
        summary=summary,
        strength=strength,
        referenced_path=referenced_path,
    )


def _read_text(path: Path) -> tuple[str | None, WorkspaceDiscoveryDiagnostic | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError) as error:
        return None, _diagnostic(
            DIAGNOSTIC_CANDIDATE_UNREADABLE,
            DIAGNOSTIC_SEVERITY_WARNING,
            "Candidate manifest could not be read.",
            path=_normalize_path_text(path),
            details={"error_type": type(error).__name__},
        )


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return _normalize_path_text(path.relative_to(root))
    except ValueError:
        return _normalize_path_text(os.path.relpath(path, root))


def _relative_candidate_path(candidate_root: Path, repository_root: Path) -> str:
    return _normalize_path_text(os.path.relpath(candidate_root, repository_root))


def _source_path_for_file(
    source_file: Path,
    *,
    source_root: Path,
    repository_root: Path,
) -> str:
    if source_root == repository_root:
        return _relative_to_root(source_file, repository_root)
    return _normalize_path_text(os.path.join(_relative_candidate_path(source_root, repository_root), _relative_to_root(source_file, source_root)))


def _normalize_identifier(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return normalized or "repository"


def _display_name(candidate_root: Path, project_names: tuple[str, ...]) -> str:
    if project_names:
        return project_names[0]
    return candidate_root.name


def _name_tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if len(token) >= 3
    )


def _has_name_similarity(current_name: str, candidate_name: str) -> bool:
    current_tokens = set(_name_tokens(current_name))
    candidate_tokens = set(_name_tokens(candidate_name))
    return bool(current_tokens and candidate_tokens and current_tokens & candidate_tokens)


def _has_marker(candidate_root: Path) -> bool:
    return any((candidate_root / marker).exists() for marker in REPOSITORY_MARKERS)


def _manifest_markers(candidate_root: Path) -> tuple[str, ...]:
    return tuple(sorted(marker for marker in REPOSITORY_MARKERS if (candidate_root / marker).exists()))


def _package_dependency_names(package_payload: Mapping[str, Any]) -> tuple[str, ...]:
    names: set[str] = set()
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        values = package_payload.get(section)
        if isinstance(values, Mapping):
            names.update(str(name) for name in values if isinstance(name, str))
    return tuple(sorted(names))


def _package_local_references(
    package_payload: Mapping[str, Any],
    package_file: Path,
    source_root: Path,
    repository_root: Path,
) -> tuple[tuple[Path, WorkspaceDiscoveryEvidence], ...]:
    references: list[tuple[Path, WorkspaceDiscoveryEvidence]] = []
    source_path = _source_path_for_file(
        package_file,
        source_root=source_root,
        repository_root=repository_root,
    )
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        values = package_payload.get(section)
        if not isinstance(values, Mapping):
            continue
        for dependency_name in sorted(values):
            dependency_value = values[dependency_name]
            if not isinstance(dependency_value, str):
                continue
            raw_path = _local_dependency_path(dependency_value)
            if raw_path is None:
                continue
            target_path = _resolve_reference_path(package_file.parent, raw_path)
            if target_path is None:
                continue
            referenced_path = _normalize_path_text(raw_path)
            references.append(
                (
                    target_path,
                    _evidence(
                        SIGNAL_LOCAL_PATH_REFERENCE,
                        source_path,
                        f"package.json {section} references local dependency {dependency_name}.",
                        EVIDENCE_STRENGTH_STRONG,
                        referenced_path=referenced_path,
                    ),
                )
            )
    return tuple(references)


def _local_dependency_path(value: str) -> str | None:
    text = value.strip()
    if text.startswith("file:"):
        text = text[len("file:") :]
    if not text.startswith(("./", "../")):
        return None
    if "$" in text or "://" in text:
        return None
    return text


def _resolve_reference_path(base_dir: Path, raw_path: str) -> Path | None:
    normalized = raw_path.strip().strip("'\"")
    if not normalized or "*" in normalized or "$" in normalized or "://" in normalized:
        return None
    return _safe_resolve(base_dir / normalized)


def _parse_package_json(
    candidate_root: Path,
    repository_root: Path,
    source_root: Path,
) -> tuple[str | None, str, tuple[tuple[Path, WorkspaceDiscoveryEvidence], ...], tuple[WorkspaceDiscoveryDiagnostic, ...]]:
    package_file = candidate_root / "package.json"
    text, read_diagnostic = _read_text(package_file)
    if text is None:
        return None, workspace_config.REPOSITORY_ROLE_UNKNOWN, (), ((read_diagnostic,) if read_diagnostic else ())
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        return None, workspace_config.REPOSITORY_ROLE_UNKNOWN, (), (
            _diagnostic(
                DIAGNOSTIC_MALFORMED_MANIFEST,
                DIAGNOSTIC_SEVERITY_WARNING,
                "package.json could not be parsed.",
                path=_source_path_for_file(package_file, source_root=source_root, repository_root=repository_root),
                details={"manifest": "package.json", "line": error.lineno},
            ),
        )
    if not isinstance(payload, Mapping):
        return None, workspace_config.REPOSITORY_ROLE_UNKNOWN, (), (
            _diagnostic(
                DIAGNOSTIC_UNSUPPORTED_OR_AMBIGUOUS_MANIFEST,
                DIAGNOSTIC_SEVERITY_WARNING,
                "package.json top-level value is not an object.",
                path=_source_path_for_file(package_file, source_root=source_root, repository_root=repository_root),
                details={"manifest": "package.json"},
            ),
        )
    dependency_names = _package_dependency_names(payload)
    role = workspace_config.REPOSITORY_ROLE_UNKNOWN
    if any(name in FRONTEND_PACKAGE_NAMES for name in dependency_names):
        role = workspace_config.REPOSITORY_ROLE_FRONTEND
    project_name = payload.get("name") if isinstance(payload.get("name"), str) else None
    references = _package_local_references(payload, package_file, source_root, repository_root)
    return project_name, role, references, ()


def _parse_pyproject_toml(
    candidate_root: Path,
    repository_root: Path,
    source_root: Path,
) -> tuple[str | None, str, tuple[WorkspaceDiscoveryDiagnostic, ...]]:
    pyproject_file = candidate_root / "pyproject.toml"
    try:
        with pyproject_file.open("rb") as handle:
            payload = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        return None, workspace_config.REPOSITORY_ROLE_UNKNOWN, (
            _diagnostic(
                DIAGNOSTIC_MALFORMED_MANIFEST,
                DIAGNOSTIC_SEVERITY_WARNING,
                "pyproject.toml could not be parsed.",
                path=_source_path_for_file(pyproject_file, source_root=source_root, repository_root=repository_root),
                details={"manifest": "pyproject.toml", "error": str(error).splitlines()[0]},
            ),
        )
    except OSError as error:
        return None, workspace_config.REPOSITORY_ROLE_UNKNOWN, (
            _diagnostic(
                DIAGNOSTIC_CANDIDATE_UNREADABLE,
                DIAGNOSTIC_SEVERITY_WARNING,
                "pyproject.toml could not be read.",
                path=_source_path_for_file(pyproject_file, source_root=source_root, repository_root=repository_root),
                details={"error_type": type(error).__name__},
            ),
        )
    project = payload.get("project") if isinstance(payload, Mapping) else None
    project_name = None
    role = workspace_config.REPOSITORY_ROLE_UNKNOWN
    if isinstance(project, Mapping):
        if isinstance(project.get("name"), str):
            project_name = project["name"]
        dependencies = project.get("dependencies")
        if isinstance(dependencies, list):
            dependency_text = "\n".join(str(item).lower() for item in dependencies)
            if any(name in dependency_text for name in PYTHON_BACKEND_DEPENDENCY_NAMES):
                role = workspace_config.REPOSITORY_ROLE_BACKEND
    return project_name, role, ()


def _parse_go_mod(
    candidate_root: Path,
    repository_root: Path,
    source_root: Path,
) -> tuple[str | None, str, tuple[WorkspaceDiscoveryDiagnostic, ...]]:
    go_mod_file = candidate_root / "go.mod"
    text, read_diagnostic = _read_text(go_mod_file)
    if text is None:
        return None, workspace_config.REPOSITORY_ROLE_UNKNOWN, ((read_diagnostic,) if read_diagnostic else ())
    module_name = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("module "):
            module_name = stripped[len("module ") :].strip()
            break
    return module_name, workspace_config.REPOSITORY_ROLE_BACKEND, ()


def _go_work_references(
    go_work_file: Path,
    source_root: Path,
    repository_root: Path,
) -> tuple[tuple[Path, WorkspaceDiscoveryEvidence], ...]:
    text, read_diagnostic = _read_text(go_work_file)
    if text is None:
        return ()
    references: list[tuple[Path, WorkspaceDiscoveryEvidence]] = []
    source_path = _source_path_for_file(
        go_work_file,
        source_root=source_root,
        repository_root=repository_root,
    )
    for line in text.splitlines():
        stripped = line.split("//", 1)[0].strip()
        if not stripped or stripped in {"use", "use ("} or stripped == ")":
            continue
        if stripped.startswith("use "):
            stripped = stripped[len("use ") :].strip()
        stripped = stripped.rstrip(",")
        if stripped.startswith(("./", "../")):
            target = _resolve_reference_path(go_work_file.parent, stripped)
            if target is not None:
                references.append(
                    (
                        target,
                        _evidence(
                            SIGNAL_WORKSPACE_FILE_MEMBERSHIP,
                            source_path,
                            "go.work use directive references a local repository.",
                            EVIDENCE_STRENGTH_STRONG,
                            referenced_path=_normalize_path_text(stripped),
                        ),
                    )
                )
    return tuple(references)


def _pnpm_workspace_references(
    workspace_file: Path,
    source_root: Path,
    repository_root: Path,
) -> tuple[tuple[Path | None, WorkspaceDiscoveryEvidence | WorkspaceDiscoveryDiagnostic], ...]:
    text, read_diagnostic = _read_text(workspace_file)
    if text is None:
        return ((None, read_diagnostic),) if read_diagnostic else ()
    references: list[tuple[Path | None, WorkspaceDiscoveryEvidence | WorkspaceDiscoveryDiagnostic]] = []
    source_path = _source_path_for_file(
        workspace_file,
        source_root=source_root,
        repository_root=repository_root,
    )
    in_packages = False
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        if stripped == "packages:":
            in_packages = True
            continue
        if in_packages and stripped.startswith("-"):
            value = stripped[1:].strip().strip("'\"")
            if "*" in value:
                references.append(
                    (
                        None,
                        _diagnostic(
                            DIAGNOSTIC_UNSUPPORTED_OR_AMBIGUOUS_MANIFEST,
                            DIAGNOSTIC_SEVERITY_INFO,
                            "pnpm-workspace.yaml wildcard package path was not expanded.",
                            path=source_path,
                            details={"referenced_path": value},
                        ),
                    )
                )
                continue
            target = _resolve_reference_path(workspace_file.parent, value)
            if target is not None:
                references.append(
                    (
                        target,
                        _evidence(
                            SIGNAL_WORKSPACE_FILE_MEMBERSHIP,
                            source_path,
                            "pnpm-workspace.yaml lists a local package path.",
                            EVIDENCE_STRENGTH_STRONG,
                            referenced_path=_normalize_path_text(value),
                        ),
                    )
                )
            continue
        if in_packages and not line.startswith((" ", "\t", "-")):
            in_packages = False
    return tuple(references)


def _docker_compose_references(
    compose_file: Path,
    source_root: Path,
    repository_root: Path,
) -> tuple[tuple[Path, WorkspaceDiscoveryEvidence], ...]:
    text, read_diagnostic = _read_text(compose_file)
    if text is None:
        return ()
    references: list[tuple[Path, WorkspaceDiscoveryEvidence]] = []
    source_path = _source_path_for_file(
        compose_file,
        source_root=source_root,
        repository_root=repository_root,
    )
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        match = re.match(r"^(build|context):\s*(.+)$", stripped)
        if match is None:
            continue
        raw_path = match.group(2).strip().strip("'\"")
        if not raw_path.startswith(("./", "../")):
            continue
        target = _resolve_reference_path(compose_file.parent, raw_path)
        if target is None:
            continue
        references.append(
            (
                target,
                _evidence(
                    SIGNAL_DOCKER_COMPOSE_BUILD_CONTEXT,
                    source_path,
                    "Docker Compose build context references a local repository.",
                    EVIDENCE_STRENGTH_STRONG,
                    referenced_path=_normalize_path_text(raw_path),
                ),
            )
        )
    return tuple(references)


def _manifest_info(
    candidate_root: Path,
    repository_root: Path,
    source_root: Path,
) -> tuple[_ManifestInfo, tuple[tuple[Path, WorkspaceDiscoveryEvidence], ...]]:
    markers = _manifest_markers(candidate_root)
    project_names: list[str] = []
    diagnostics: list[WorkspaceDiscoveryDiagnostic] = []
    references: list[tuple[Path, WorkspaceDiscoveryEvidence]] = []
    roles: list[str] = []

    if (candidate_root / "package.json").is_file():
        package_name, package_role, package_references, package_diagnostics = _parse_package_json(
            candidate_root,
            repository_root,
            source_root,
        )
        if package_name:
            project_names.append(package_name)
        if package_role != workspace_config.REPOSITORY_ROLE_UNKNOWN:
            roles.append(package_role)
        references.extend(package_references)
        diagnostics.extend(package_diagnostics)

    if (candidate_root / "pyproject.toml").is_file():
        pyproject_name, pyproject_role, pyproject_diagnostics = _parse_pyproject_toml(
            candidate_root,
            repository_root,
            source_root,
        )
        if pyproject_name:
            project_names.append(pyproject_name)
        if pyproject_role != workspace_config.REPOSITORY_ROLE_UNKNOWN:
            roles.append(pyproject_role)
        diagnostics.extend(pyproject_diagnostics)

    if (candidate_root / "go.mod").is_file():
        module_name, go_role, go_diagnostics = _parse_go_mod(
            candidate_root,
            repository_root,
            source_root,
        )
        if module_name:
            project_names.append(module_name)
        if go_role != workspace_config.REPOSITORY_ROLE_UNKNOWN:
            roles.append(go_role)
        diagnostics.extend(go_diagnostics)

    if (candidate_root / "angular.json").is_file():
        roles.append(workspace_config.REPOSITORY_ROLE_FRONTEND)

    if any((candidate_root / name).is_file() for name in DOCKER_COMPOSE_FILES):
        if not roles:
            roles.append(workspace_config.REPOSITORY_ROLE_INFRASTRUCTURE)

    role = _choose_role(tuple(roles))
    return (
        _ManifestInfo(
            markers=markers,
            project_names=tuple(sorted(set(project_names))),
            probable_role=role,
            diagnostics=tuple(diagnostics),
        ),
        tuple(references),
    )


def _choose_role(roles: tuple[str, ...]) -> str:
    for role in (
        workspace_config.REPOSITORY_ROLE_FRONTEND,
        workspace_config.REPOSITORY_ROLE_BACKEND,
        workspace_config.REPOSITORY_ROLE_INFRASTRUCTURE,
    ):
        if role in roles:
            return role
    return workspace_config.REPOSITORY_ROLE_UNKNOWN


def _source_references(
    source_root: Path,
    repository_root: Path,
) -> tuple[tuple[Path | None, WorkspaceDiscoveryEvidence | WorkspaceDiscoveryDiagnostic], ...]:
    items: list[tuple[Path | None, WorkspaceDiscoveryEvidence | WorkspaceDiscoveryDiagnostic]] = []
    if (source_root / "package.json").is_file():
        _name, _role, references, diagnostics = _parse_package_json(
            source_root,
            repository_root,
            source_root,
        )
        items.extend((target, evidence) for target, evidence in references)
        items.extend((None, diagnostic) for diagnostic in diagnostics)
    if (source_root / "go.work").is_file():
        items.extend(_go_work_references(source_root / "go.work", source_root, repository_root))
    if (source_root / "pnpm-workspace.yaml").is_file():
        items.extend(_pnpm_workspace_references(source_root / "pnpm-workspace.yaml", source_root, repository_root))
    for compose_name in DOCKER_COMPOSE_FILES:
        compose_file = source_root / compose_name
        if compose_file.is_file():
            items.extend(_docker_compose_references(compose_file, source_root, repository_root))
    return tuple(items)


def _configured_paths(
    repository_root: Path,
    existing_workspace_config: Any,
) -> tuple[Path, ...]:
    if existing_workspace_config is None:
        return ()
    try:
        normalized = workspace_config.validate_workspace_config(existing_workspace_config)
    except ValueError:
        return ()
    paths: list[Path] = []
    for repository in normalized["repositories"]:
        raw_path = repository.get("path")
        if not isinstance(raw_path, str):
            continue
        paths.append(_safe_resolve(repository_root / raw_path))
    return tuple(sorted(set(paths), key=lambda item: _normalize_path_text(item)))


def _path_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _target_matches_candidate(target: Path, candidate_root: Path) -> bool:
    resolved_target = _safe_resolve(target)
    return resolved_target == candidate_root or _path_inside(resolved_target, candidate_root)


def _current_project_names(repository_root: Path) -> tuple[str, ...]:
    info, _references = _manifest_info(repository_root, repository_root, repository_root)
    if info.project_names:
        return info.project_names
    return (repository_root.name,)


def _candidate_evidence(
    candidate_root: Path,
    repository_root: Path,
    search_root: Path,
    current_names: tuple[str, ...],
    current_references: tuple[tuple[Path | None, WorkspaceDiscoveryEvidence | WorkspaceDiscoveryDiagnostic], ...],
) -> _CandidateAnalysis:
    relative_path = _relative_candidate_path(candidate_root, repository_root)
    resolved_root = _safe_resolve(candidate_root)
    manifest_info, candidate_references = _manifest_info(
        candidate_root,
        repository_root,
        candidate_root,
    )
    evidence_items: list[WorkspaceDiscoveryEvidence] = [
        _evidence(
            SIGNAL_SIBLING_PROXIMITY,
            ".",
            "Candidate is a direct sibling under the bounded search root.",
            EVIDENCE_STRENGTH_WEAK,
            referenced_path=relative_path,
        )
    ]
    diagnostics: list[WorkspaceDiscoveryDiagnostic] = list(manifest_info.diagnostics)

    if (candidate_root / ".git").exists():
        evidence_items.append(
            _evidence(
                SIGNAL_GIT_MARKER,
                relative_path,
                "Candidate contains a .git repository marker.",
                EVIDENCE_STRENGTH_WEAK,
                referenced_path=relative_path,
            )
        )

    for marker in manifest_info.markers:
        if marker == ".git":
            continue
        evidence_items.append(
            _evidence(
                SIGNAL_PROJECT_MANIFEST,
                _normalize_path_text(os.path.join(relative_path, marker)),
                f"Candidate contains project marker {marker}.",
                EVIDENCE_STRENGTH_MEDIUM,
                referenced_path=relative_path,
            )
        )

    for target, item in current_references:
        if isinstance(item, WorkspaceDiscoveryDiagnostic):
            diagnostics.append(item)
            continue
        if target is not None and _target_matches_candidate(target, resolved_root):
            evidence_items.append(item)

    for target, item in candidate_references:
        if _target_matches_candidate(target, _safe_resolve(repository_root)):
            evidence_items.append(item)

    candidate_names = manifest_info.project_names or (candidate_root.name,)
    if any(_has_name_similarity(current_name, candidate_name) for current_name in current_names for candidate_name in candidate_names):
        evidence_items.append(
            _evidence(
                SIGNAL_NAME_SIMILARITY,
                ".",
                "Repository names share a normalized token.",
                EVIDENCE_STRENGTH_WEAK,
                referenced_path=relative_path,
            )
        )

    suggested_id = _normalize_identifier(candidate_root.name)
    display_name = _display_name(candidate_root, manifest_info.project_names)
    return _CandidateAnalysis(
        root=candidate_root,
        resolved_root=resolved_root,
        relative_path=relative_path,
        suggested_id=suggested_id,
        display_name=display_name,
        probable_role=manifest_info.probable_role,
        evidence=tuple(sorted(set(evidence_items), key=_evidence_sort_key)),
        diagnostics=tuple(diagnostics),
    )


def _score_evidence(evidence_items: tuple[WorkspaceDiscoveryEvidence, ...]) -> float:
    score = 0.0
    seen_signal_types: set[str] = set()
    for item in evidence_items:
        if item.signal_type in seen_signal_types:
            continue
        seen_signal_types.add(item.signal_type)
        score += EVIDENCE_WEIGHTS[item.signal_type]
    if seen_signal_types <= {SIGNAL_SIBLING_PROXIMITY, SIGNAL_NAME_SIMILARITY, SIGNAL_GIT_MARKER}:
        score = min(score, 0.30)
    return round(min(score, 0.95), 3)


def _confidence_label(score: float) -> str:
    if score >= 0.65:
        return CONFIDENCE_HIGH
    if score >= 0.35:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _bounded_evidence(
    evidence_items: tuple[WorkspaceDiscoveryEvidence, ...],
    max_evidence_per_candidate: int,
    candidate_path: str,
) -> tuple[tuple[WorkspaceDiscoveryEvidence, ...], tuple[str, ...], tuple[WorkspaceDiscoveryDiagnostic, ...]]:
    if len(evidence_items) <= max_evidence_per_candidate:
        return evidence_items, (), ()
    omitted = len(evidence_items) - max_evidence_per_candidate
    warning = f"evidence cap reached; omitted {omitted} item(s)."
    diagnostic = _diagnostic(
        DIAGNOSTIC_EVIDENCE_CAP_REACHED,
        DIAGNOSTIC_SEVERITY_INFO,
        "Candidate evidence was truncated.",
        path=candidate_path,
        details={
            "max_evidence_per_candidate": max_evidence_per_candidate,
            "omitted": omitted,
        },
    )
    return evidence_items[:max_evidence_per_candidate], (warning,), (diagnostic,)


def _build_suggestion(
    analysis: _CandidateAnalysis,
    max_evidence_per_candidate: int,
) -> tuple[WorkspaceRepositorySuggestion, tuple[WorkspaceDiscoveryDiagnostic, ...]]:
    score = _score_evidence(analysis.evidence)
    evidence_items, warnings, cap_diagnostics = _bounded_evidence(
        analysis.evidence,
        max_evidence_per_candidate,
        analysis.relative_path,
    )
    suggestion = WorkspaceRepositorySuggestion(
        path=analysis.relative_path,
        suggested_id=analysis.suggested_id,
        display_name=analysis.display_name,
        probable_role=analysis.probable_role,
        confidence=_confidence_label(score),
        confidence_score=score,
        evidence=evidence_items,
        warnings=warnings,
    )
    return suggestion, (*analysis.diagnostics, *cap_diagnostics)


def _candidate_dirs(
    repository_root: Path,
    search_root: Path,
) -> tuple[Path, tuple[WorkspaceDiscoveryDiagnostic, ...]]:
    diagnostics: list[WorkspaceDiscoveryDiagnostic] = []
    candidates: list[Path] = []
    seen: set[Path] = set()
    try:
        entries = sorted(search_root.iterdir(), key=lambda item: item.name.lower())
    except OSError as error:
        return (), (
            _diagnostic(
                DIAGNOSTIC_SEARCH_ROOT_UNREADABLE,
                DIAGNOSTIC_SEVERITY_ERROR,
                "Search root could not be read.",
                path=_normalize_path_text(search_root),
                details={"error_type": type(error).__name__},
            ),
        )

    resolved_repository_root = _safe_resolve(repository_root)
    resolved_search_root = _safe_resolve(search_root)
    for entry in entries:
        if _is_ignored_directory_name(entry.name):
            continue
        try:
            if entry.is_symlink():
                diagnostics.append(
                    _diagnostic(
                        DIAGNOSTIC_SYMLINK_SKIPPED,
                        DIAGNOSTIC_SEVERITY_INFO,
                        "Symlink candidate was skipped.",
                        path=_normalize_path_text(entry),
                    )
                )
                continue
            if not entry.is_dir():
                continue
            resolved_entry = _safe_resolve(entry)
        except OSError as error:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_CANDIDATE_UNREADABLE,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Candidate directory could not be inspected.",
                    path=_normalize_path_text(entry),
                    details={"error_type": type(error).__name__},
                )
            )
            continue
        if resolved_entry == resolved_repository_root:
            continue
        if not _path_inside(resolved_entry, resolved_search_root):
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_PATH_ESCAPED_SEARCH_BOUNDARY,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Candidate path escaped the search boundary.",
                    path=_normalize_path_text(entry),
                )
            )
            continue
        if resolved_entry in seen:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_DUPLICATE_CANDIDATE_PATH,
                    DIAGNOSTIC_SEVERITY_INFO,
                    "Duplicate candidate path was skipped.",
                    path=_normalize_path_text(entry),
                )
            )
            continue
        seen.add(resolved_entry)
        if _has_marker(entry):
            candidates.append(entry)
    return tuple(candidates), tuple(diagnostics)


def _valid_limit(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _empty_result(
    repository_root: Path,
    search_root: Path,
    diagnostics: Iterable[WorkspaceDiscoveryDiagnostic],
) -> WorkspaceDiscoveryResult:
    return WorkspaceDiscoveryResult(
        repository_root=_normalize_path_text(repository_root),
        search_root=_normalize_path_text(search_root),
        candidates=(),
        diagnostics=tuple(diagnostics),
    )


def discover_workspace_repositories(
    repository_root: str | Path,
    *,
    search_root: str | Path | None = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    max_evidence_per_candidate: int = DEFAULT_MAX_EVIDENCE_PER_CANDIDATE,
    existing_workspace_config: Any = None,
) -> WorkspaceDiscoveryResult:
    """Return bounded nearby repository suggestions without changing config.

    Scoring is deterministic and intentionally simple: strong explicit
    workspace membership or local path references carry the most weight;
    sibling proximity, .git markers, and name similarity are weak and cannot
    produce high confidence by themselves.
    """

    max_candidates = _valid_limit(max_candidates, "max_candidates")
    max_evidence_per_candidate = _valid_limit(
        max_evidence_per_candidate,
        "max_evidence_per_candidate",
    )
    repository_path = Path(repository_root)
    search_path = Path(search_root) if search_root is not None else repository_path.parent
    normalized_repository = _normalize_path_text(repository_path)
    normalized_search = _normalize_path_text(search_path)

    if not repository_path.exists():
        return _empty_result(
            repository_path,
            search_path,
            (
                _diagnostic(
                    DIAGNOSTIC_REPOSITORY_ROOT_MISSING,
                    DIAGNOSTIC_SEVERITY_ERROR,
                    "Repository root does not exist.",
                    path=normalized_repository,
                ),
            ),
        )
    if not repository_path.is_dir():
        return _empty_result(
            repository_path,
            search_path,
            (
                _diagnostic(
                    DIAGNOSTIC_REPOSITORY_ROOT_NOT_DIRECTORY,
                    DIAGNOSTIC_SEVERITY_ERROR,
                    "Repository root is not a directory.",
                    path=normalized_repository,
                ),
            ),
        )
    if not search_path.exists():
        return _empty_result(
            repository_path,
            search_path,
            (
                _diagnostic(
                    DIAGNOSTIC_SEARCH_ROOT_MISSING,
                    DIAGNOSTIC_SEVERITY_ERROR,
                    "Search root does not exist.",
                    path=normalized_search,
                ),
            ),
        )
    if not search_path.is_dir():
        return _empty_result(
            repository_path,
            search_path,
            (
                _diagnostic(
                    DIAGNOSTIC_SEARCH_ROOT_NOT_DIRECTORY,
                    DIAGNOSTIC_SEVERITY_ERROR,
                    "Search root is not a directory.",
                    path=normalized_search,
                ),
            ),
        )

    resolved_repository = _safe_resolve(repository_path)
    resolved_search = _safe_resolve(search_path)
    if search_root is not None and not _path_inside(resolved_repository, resolved_search):
        return _empty_result(
            repository_path,
            search_path,
            (
                _diagnostic(
                    DIAGNOSTIC_REPOSITORY_OUTSIDE_SEARCH_ROOT,
                    DIAGNOSTIC_SEVERITY_ERROR,
                    "Repository root is outside the explicit search root.",
                    path=normalized_repository,
                    details={"search_root": normalized_search},
                ),
            ),
        )

    candidate_dirs, diagnostics = _candidate_dirs(repository_path, search_path)
    configured_paths = set(_configured_paths(repository_path, existing_workspace_config))
    current_references = _source_references(repository_path, repository_path)
    current_names = _current_project_names(repository_path)

    suggestions: list[WorkspaceRepositorySuggestion] = []
    all_diagnostics: list[WorkspaceDiscoveryDiagnostic] = list(diagnostics)
    for candidate_dir in candidate_dirs:
        resolved_candidate = _safe_resolve(candidate_dir)
        if resolved_candidate in configured_paths:
            continue
        analysis = _candidate_evidence(
            candidate_dir,
            repository_path,
            search_path,
            current_names,
            current_references,
        )
        suggestion, suggestion_diagnostics = _build_suggestion(
            analysis,
            max_evidence_per_candidate,
        )
        suggestions.append(suggestion)
        all_diagnostics.extend(suggestion_diagnostics)

    ordered = tuple(sorted(suggestions, key=_candidate_sort_key))
    if len(ordered) > max_candidates:
        all_diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_CANDIDATE_CAP_REACHED,
                DIAGNOSTIC_SEVERITY_WARNING,
                "Workspace discovery candidate cap was reached.",
                path=normalized_search,
                details={
                    "max_candidates": max_candidates,
                    "omitted": len(ordered) - max_candidates,
                },
            )
        )
        ordered = ordered[:max_candidates]

    return WorkspaceDiscoveryResult(
        repository_root=_normalize_path_text(repository_path),
        search_root=_normalize_path_text(search_path),
        candidates=ordered,
        diagnostics=tuple(all_diagnostics),
    )


def workspace_discovery_result_to_dict(
    result: WorkspaceDiscoveryResult,
) -> dict[str, Any]:
    """Return a stable JSON-ready discovery result."""

    if not isinstance(result, WorkspaceDiscoveryResult):
        raise TypeError("result must be a WorkspaceDiscoveryResult")
    return result.to_dict()
