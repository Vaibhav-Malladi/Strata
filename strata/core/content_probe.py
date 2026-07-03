"""Strictly bounded content windows for candidate evaluation probes."""

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Iterable

from strata.core.probe_pool import ProbePool, ProbePoolEntry
from strata.core.stage_report import StageReport, elapsed_milliseconds


DEFAULT_MAX_FILES = 20
DEFAULT_MAX_BYTES_PER_FILE = 4 * 1024
DEFAULT_MAX_TOTAL_BYTES = 32 * 1024
DEFAULT_MAX_FILE_SIZE = 256 * 1024

_TASK_STOPWORDS = {
    "a",
    "add",
    "an",
    "and",
    "change",
    "fix",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "update",
    "with",
}


def _validate_positive_integer(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


@dataclass(frozen=True, slots=True)
class ContentProbeCaps:
    max_files: int = DEFAULT_MAX_FILES
    max_bytes_per_file: int = DEFAULT_MAX_BYTES_PER_FILE
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    max_file_size: int = DEFAULT_MAX_FILE_SIZE

    def __post_init__(self) -> None:
        for name in (
            "max_files",
            "max_bytes_per_file",
            "max_total_bytes",
            "max_file_size",
        ):
            _validate_positive_integer(getattr(self, name), name)

    def to_dict(self) -> dict[str, int]:
        """Return a stable JSON-ready cap mapping."""

        return {
            "max_files": self.max_files,
            "max_bytes_per_file": self.max_bytes_per_file,
            "max_total_bytes": self.max_total_bytes,
            "max_file_size": self.max_file_size,
        }


DEFAULT_CONTENT_PROBE_CAPS = ContentProbeCaps()


@dataclass(frozen=True, slots=True)
class ContentProbeFileResult:
    path: str
    probe_relevance: float
    evidence: tuple[str, ...]
    signals: tuple[str, ...]
    confidence: str
    bytes_read: int
    skipped_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready per-file probe result."""

        return {
            "path": self.path,
            "probe_relevance": self.probe_relevance,
            "evidence": list(self.evidence),
            "signals": list(self.signals),
            "confidence": self.confidence,
            "bytes_read": self.bytes_read,
            "skipped_reason": self.skipped_reason,
        }


@dataclass(frozen=True, slots=True)
class ContentProbeResult:
    files: tuple[ContentProbeFileResult, ...]
    caps: ContentProbeCaps
    stage_report: StageReport

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready aggregate probe result."""

        return {
            "caps": self.caps.to_dict(),
            "files": [file_result.to_dict() for file_result in self.files],
            "stage_report": self.stage_report.to_dict(),
        }


def probe_content(
    root: str | Path,
    entries: ProbePool | Iterable[ProbePoolEntry | str | Path],
    task: str,
    *,
    caps: ContentProbeCaps = DEFAULT_CONTENT_PROBE_CAPS,
    clock_ns: Callable[[], int] | None = None,
) -> ContentProbeResult:
    """Read one bounded content window for each eligible candidate path."""

    if not isinstance(caps, ContentProbeCaps):
        raise TypeError("caps must be ContentProbeCaps")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")
    paths = _normalize_input_paths(entries)
    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(f"content probe root does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"content probe root is not a directory: {root_path}")
    resolved_root = root_path.resolve()
    task_tokens = _tokens(task) - _TASK_STOPWORDS
    start_ns = clock_ns() if clock_ns is not None else None

    results: list[ContentProbeFileResult] = []
    total_bytes_read = 0
    files_touched = 0
    open_attempts = 0
    for path in paths:
        if open_attempts >= caps.max_files:
            results.append(_skipped_result(path, "max_files_cap"))
            continue
        remaining_bytes = caps.max_total_bytes - total_bytes_read
        if remaining_bytes <= 0:
            results.append(_skipped_result(path, "max_total_bytes_cap"))
            continue

        files_touched += 1
        target, unsafe_reason = _resolve_target(resolved_root, path)
        if unsafe_reason is not None:
            results.append(_skipped_result(path, unsafe_reason))
            continue
        try:
            metadata = target.stat()
        except OSError:
            results.append(_skipped_result(path, "unreadable_metadata"))
            continue
        if not target.is_file():
            results.append(_skipped_result(path, "not_regular_file"))
            continue
        if metadata.st_size > caps.max_file_size:
            results.append(_skipped_result(path, "file_too_large"))
            continue

        read_limit = min(caps.max_bytes_per_file, remaining_bytes)
        open_attempts += 1
        try:
            with target.open("rb") as handle:
                content = handle.read(read_limit)
        except OSError:
            results.append(_skipped_result(path, "unreadable_content"))
            continue

        bytes_read = len(content)
        total_bytes_read += bytes_read
        if b"\x00" in content:
            results.append(
                _skipped_result(path, "binary_content", bytes_read=bytes_read)
            )
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            results.append(
                _skipped_result(path, "non_utf8_content", bytes_read=bytes_read)
            )
            continue

        relevance, evidence, signals, confidence = _score_window(
            text,
            task_tokens,
            truncated=metadata.st_size > bytes_read,
        )
        results.append(
            ContentProbeFileResult(
                path=path,
                probe_relevance=relevance,
                evidence=evidence,
                signals=signals,
                confidence=confidence,
                bytes_read=bytes_read,
                skipped_reason=None,
            )
        )

    skipped_items = tuple(
        f"{result.path}: {result.skipped_reason}"
        for result in results
        if result.skipped_reason is not None
    )
    skipped_reasons = {
        result.skipped_reason
        for result in results
        if result.skipped_reason is not None
    }
    warnings: list[str] = []
    if skipped_reasons & {"max_files_cap", "max_total_bytes_cap"}:
        warnings.append("one or more content probe caps were reached")
    if skipped_reasons - {"max_files_cap", "max_total_bytes_cap"}:
        warnings.append("one or more files could not be content probed")

    probed_results = tuple(
        result for result in results if result.skipped_reason is None
    )
    average_relevance = (
        sum(result.probe_relevance for result in probed_results)
        / len(probed_results)
        if probed_results
        else 0.0
    )
    elapsed_ms = 0.0
    if clock_ns is not None and start_ns is not None:
        elapsed_ms = elapsed_milliseconds(start_ns, clock_ns())
    stage_confidence = "unknown"
    if probed_results:
        stage_confidence = "medium" if skipped_items else "high"

    stage_report = StageReport(
        stage_name="content_probe",
        inputs={
            "task": task,
            "requested_paths": len(paths),
            "caps": caps.to_dict(),
        },
        outputs={
            "probed_files": len(probed_results),
            "skipped_files": len(skipped_items),
        },
        metrics={"average_probe_relevance": average_relevance},
        warnings=tuple(warnings),
        skipped_items=skipped_items,
        confidence=stage_confidence,
        elapsed_ms=elapsed_ms,
        bytes_read=total_bytes_read,
        files_touched=files_touched,
    )
    return ContentProbeResult(
        files=tuple(results),
        caps=caps,
        stage_report=stage_report,
    )


def _score_window(
    text: str,
    task_tokens: set[str],
    *,
    truncated: bool,
) -> tuple[float, tuple[str, ...], tuple[str, ...], str]:
    content_tokens = _tokens(text)
    matched_terms = sorted(task_tokens & content_tokens)
    coverage = len(matched_terms) / len(task_tokens) if task_tokens else 0.0
    evidence: list[str] = []
    signals: list[str] = []
    if matched_terms:
        evidence.append(f"task terms in content: {', '.join(matched_terms)}")
        signals.append("task_terms")

    has_import_export = bool(
        re.search(
            r"(?m)^\s*(?:from\s+\S+\s+import\s+|import\s+|export\s+)",
            text,
        )
    )
    if has_import_export:
        evidence.append("contains import or export declaration")
        signals.append("import_export")

    has_signature = bool(
        re.search(
            r"(?m)^\s*(?:(?:async\s+)?(?:def|class|function)\s+\w+|"
            r"export\s+(?:default\s+)?(?:class|function|const)\s+)",
            text,
        )
    )
    if has_signature:
        evidence.append("contains class or function signature")
        signals.append("signature")

    has_route_framework = bool(
        re.search(
            r"(?i)@(component|directive|injectable|route|get|post|put|delete)\b|"
            r"\b(?:router|routes?)\s*[.(=:]|\bpath\s*\(",
            text,
        )
    )
    if has_route_framework:
        evidence.append("contains route or framework declaration")
        signals.append("route_framework")

    stripped = text.lstrip()
    if stripped.startswith(("#", "//", "/*", '"""', "'''")):
        signals.append("top_comment")
    if truncated:
        signals.append("window_truncated")

    relevance = min(
        1.0,
        0.7 * coverage
        + 0.1 * int(has_import_export)
        + 0.1 * int(has_signature)
        + 0.1 * int(has_route_framework),
    )
    confidence = "unknown"
    if relevance >= 0.7:
        confidence = "high"
    elif relevance >= 0.4:
        confidence = "medium"
    elif relevance > 0:
        confidence = "low"
    return relevance, tuple(evidence), tuple(signals), confidence


def _normalize_input_paths(
    entries: ProbePool | Iterable[ProbePoolEntry | str | Path],
) -> tuple[str, ...]:
    values: Iterable[ProbePoolEntry | str | Path]
    if isinstance(entries, ProbePool):
        values = entries.entries
    else:
        if isinstance(entries, (str, Path, ProbePoolEntry)):
            raise TypeError("entries must be a ProbePool or iterable of paths")
        values = entries

    paths: list[str] = []
    for index, value in enumerate(values):
        raw_path = value.path if isinstance(value, ProbePoolEntry) else value
        path = _normalize_path(raw_path, f"entries[{index}]")
        if path not in paths:
            paths.append(path)
    return tuple(paths)


def _normalize_path(value: str | Path, location: str) -> str:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{location} must be a string, Path, or ProbePoolEntry")
    raw_path = str(value)
    if not raw_path or raw_path != raw_path.strip():
        raise ValueError(f"{location} must be a non-empty path without outer whitespace")
    normalized = raw_path.replace("\\", "/")
    path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(raw_path)
    if path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"{location} must be relative")
    if ".." in path.parts:
        raise ValueError(f"{location} must not escape its root with '..'")
    normalized = path.as_posix()
    if normalized == ".":
        raise ValueError(f"{location} must name a file")
    return normalized


def _resolve_target(root: Path, path: str) -> tuple[Path, str | None]:
    candidate = root.joinpath(*PurePosixPath(path).parts)
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        return candidate, "missing_file"
    except OSError:
        return candidate, "unreadable_metadata"
    try:
        resolved.relative_to(root)
    except ValueError:
        return resolved, "outside_root"
    return resolved, None


def _skipped_result(
    path: str,
    reason: str,
    *,
    bytes_read: int = 0,
) -> ContentProbeFileResult:
    return ContentProbeFileResult(
        path=path,
        probe_relevance=0.0,
        evidence=(),
        signals=(),
        confidence="unknown",
        bytes_read=bytes_read,
        skipped_reason=reason,
    )


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))

