"""Normalized score contract for future bounded content probes."""

import math
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

from strata.core.stage_report import CONFIDENCE_LEVELS


def _validate_normalized(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    if normalized < 0.0 or normalized > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return normalized


@dataclass(frozen=True, slots=True)
class ProbeScoreWeights:
    cheap_weight: float = 0.35
    probe_weight: float = 0.30
    structural_weight: float = 0.20
    cost_weight: float = 0.15

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cheap_weight",
            _validate_normalized(self.cheap_weight, "cheap_weight"),
        )
        object.__setattr__(
            self,
            "probe_weight",
            _validate_normalized(self.probe_weight, "probe_weight"),
        )
        object.__setattr__(
            self,
            "structural_weight",
            _validate_normalized(self.structural_weight, "structural_weight"),
        )
        object.__setattr__(
            self,
            "cost_weight",
            _validate_normalized(self.cost_weight, "cost_weight"),
        )
        total = (
            self.cheap_weight
            + self.probe_weight
            + self.structural_weight
            + self.cost_weight
        )
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("probe score weights must sum to 1.0")
        if self.cheap_weight + self.probe_weight + self.structural_weight <= 0:
            raise ValueError("probe score weights must include relevance weight")

    def to_dict(self) -> dict[str, float]:
        """Return a stable JSON-ready weight mapping."""

        return {
            "cheap_weight": self.cheap_weight,
            "probe_weight": self.probe_weight,
            "structural_weight": self.structural_weight,
            "cost_weight": self.cost_weight,
        }


DEFAULT_PROBE_SCORE_WEIGHTS = ProbeScoreWeights()


@dataclass(frozen=True, slots=True)
class ProbeScoreResult:
    path: str
    cheap_relevance: float
    probe_relevance: float
    structural_relevance: float
    normalized_cost: float
    final_score: float
    confidence: str
    weights: ProbeScoreWeights

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready score result."""

        return {
            "path": self.path,
            "cheap_relevance": self.cheap_relevance,
            "probe_relevance": self.probe_relevance,
            "structural_relevance": self.structural_relevance,
            "normalized_cost": self.normalized_cost,
            "final_score": self.final_score,
            "confidence": self.confidence,
            "weights": self.weights.to_dict(),
        }


def score_probe_entry(
    path: str | Path,
    *,
    cheap_relevance: float,
    probe_relevance: float,
    structural_relevance: float,
    normalized_cost: float,
    confidence: str = "unknown",
    weights: ProbeScoreWeights = DEFAULT_PROBE_SCORE_WEIGHTS,
) -> ProbeScoreResult:
    """Validate normalized components and calculate one final probe score."""

    normalized_path = _normalize_path(path)
    cheap = _validate_normalized(cheap_relevance, "cheap_relevance")
    probe = _validate_normalized(probe_relevance, "probe_relevance")
    structural = _validate_normalized(
        structural_relevance,
        "structural_relevance",
    )
    cost = _validate_normalized(normalized_cost, "normalized_cost")
    if confidence not in CONFIDENCE_LEVELS:
        allowed = ", ".join(CONFIDENCE_LEVELS)
        raise ValueError(f"confidence must be one of: {allowed}")
    if not isinstance(weights, ProbeScoreWeights):
        raise TypeError("weights must be ProbeScoreWeights")

    final_score = (
        weights.cheap_weight * cheap
        + weights.probe_weight * probe
        + weights.structural_weight * structural
        - weights.cost_weight * cost
    )
    return ProbeScoreResult(
        path=normalized_path,
        cheap_relevance=cheap,
        probe_relevance=probe,
        structural_relevance=structural,
        normalized_cost=cost,
        final_score=final_score,
        confidence=confidence,
        weights=weights,
    )


def sort_probe_scores(
    results: Iterable[ProbeScoreResult],
) -> tuple[ProbeScoreResult, ...]:
    """Sort by descending score with deterministic path/component tie-breakers."""

    validated: list[ProbeScoreResult] = []
    for index, result in enumerate(results):
        if not isinstance(result, ProbeScoreResult):
            raise TypeError(f"results[{index}] must be a ProbeScoreResult")
        validated.append(result)
    return tuple(
        sorted(
            validated,
            key=lambda result: (
                -result.final_score,
                result.path,
                -result.cheap_relevance,
                -result.probe_relevance,
                -result.structural_relevance,
                result.normalized_cost,
            ),
        )
    )


def _normalize_path(value: str | Path) -> str:
    if not isinstance(value, (str, Path)):
        raise TypeError("path must be a string or Path")
    raw_path = str(value)
    if not raw_path or raw_path != raw_path.strip():
        raise ValueError("path must be non-empty without outer whitespace")
    normalized = raw_path.replace("\\", "/")
    path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(raw_path)
    if path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError("path must be relative")
    if ".." in path.parts:
        raise ValueError("path must not escape its root with '..'")
    normalized = path.as_posix()
    if normalized == ".":
        raise ValueError("path must name a file")
    return normalized
