"""Shared stage-level reporting and lightweight measurement helpers."""

import math
import time
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping


CONFIDENCE_LEVELS = ("unknown", "low", "medium", "high")


@dataclass(frozen=True, slots=True)
class StageReport:
    stage_name: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    outputs: Mapping[str, Any] = field(default_factory=dict)
    metrics: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    skipped_items: tuple[str, ...] = ()
    confidence: str = "unknown"
    elapsed_ms: float = 0.0
    bytes_read: int = 0
    files_touched: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stage_name",
            _validate_nonempty_string(self.stage_name, "stage_name"),
        )
        object.__setattr__(self, "inputs", _freeze_mapping(self.inputs, "inputs"))
        object.__setattr__(self, "outputs", _freeze_mapping(self.outputs, "outputs"))
        object.__setattr__(self, "metrics", _freeze_mapping(self.metrics, "metrics"))
        object.__setattr__(
            self,
            "warnings",
            _validate_messages(self.warnings, "warnings"),
        )
        object.__setattr__(
            self,
            "skipped_items",
            _validate_messages(self.skipped_items, "skipped_items"),
        )
        if self.confidence not in CONFIDENCE_LEVELS:
            allowed = ", ".join(CONFIDENCE_LEVELS)
            raise ValueError(f"confidence must be one of: {allowed}")
        object.__setattr__(
            self,
            "elapsed_ms",
            _validate_elapsed_ms(self.elapsed_ms),
        )
        object.__setattr__(
            self,
            "bytes_read",
            _validate_nonnegative_integer(self.bytes_read, "bytes_read"),
        )
        object.__setattr__(
            self,
            "files_touched",
            _validate_nonnegative_integer(self.files_touched, "files_touched"),
        )

    def with_metric(self, name: str, value: Any) -> "StageReport":
        """Return a report containing one added or replaced metric."""

        metric_name = _validate_nonempty_string(name, "metric name")
        metrics = dict(self.metrics)
        metrics[metric_name] = value
        return replace(self, metrics=metrics)

    def with_warning(self, warning: str) -> "StageReport":
        """Return a report with a warning appended in observation order."""

        return replace(self, warnings=(*self.warnings, warning))

    def with_skipped_item(self, item: str) -> "StageReport":
        """Return a report with a skipped item appended in observation order."""

        return replace(self, skipped_items=(*self.skipped_items, item))

    def to_dict(self) -> dict[str, Any]:
        """Return the stable, JSON-ready representation of this report."""

        return {
            "stage_name": self.stage_name,
            "inputs": _thaw_json(self.inputs),
            "outputs": _thaw_json(self.outputs),
            "metrics": _thaw_json(self.metrics),
            "warnings": list(self.warnings),
            "skipped_items": list(self.skipped_items),
            "confidence": self.confidence,
            "elapsed_ms": self.elapsed_ms,
            "bytes_read": self.bytes_read,
            "files_touched": self.files_touched,
        }


def create_stage_report(stage_name: str, **values: Any) -> StageReport:
    """Create and validate an immutable stage report."""

    return StageReport(stage_name=stage_name, **values)


def stage_report_to_dict(report: StageReport) -> dict[str, Any]:
    """Convert a stage report to its stable JSON-ready shape."""

    if not isinstance(report, StageReport):
        raise TypeError("report must be a StageReport")
    return report.to_dict()


def elapsed_milliseconds(start_ns: int, end_ns: int | None = None) -> float:
    """Return elapsed milliseconds between monotonic nanosecond readings."""

    start = _validate_nonnegative_integer(start_ns, "start_ns")
    end = time.perf_counter_ns() if end_ns is None else end_ns
    end = _validate_nonnegative_integer(end, "end_ns")
    if end < start:
        raise ValueError("end_ns must be greater than or equal to start_ns")
    return (end - start) / 1_000_000


def _freeze_mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{location} must be a mapping")

    for key in value:
        _validate_nonempty_string(key, f"{location} key")

    normalized: dict[str, Any] = {}
    for key in sorted(value):
        normalized[key] = _freeze_json(value[key], f"{location}.{key}")
    return MappingProxyType(normalized)


def _freeze_json(value: Any, location: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{location} must contain finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        return _freeze_mapping(value, location)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, f"{location}[{index}]")
            for index, item in enumerate(value)
        )
    raise TypeError(f"{location} must contain only JSON-ready values")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _validate_messages(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        messages = tuple(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    for index, message in enumerate(messages):
        _validate_nonempty_string(message, f"{name}[{index}]")
    return messages


def _validate_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{name} must not have surrounding whitespace")
    return value


def _validate_elapsed_ms(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("elapsed_ms must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError("elapsed_ms must be a finite non-negative number")
    return normalized


def _validate_nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value
