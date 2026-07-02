from dataclasses import dataclass
from typing import Iterable

from strata.core.inventory import InventoryRecord, is_generated_path


MAX_FRAMEWORK_REASONS = 8
_DETECTION_THRESHOLD = 2
_FRAMEWORK_ORDER = {"react": 0, "angular": 1}
_REACT_EXTENSIONS = {".jsx", ".tsx"}
_LOCKFILES = {
    "bun.lock",
    "bun.lockb",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}


@dataclass(frozen=True, slots=True)
class FrontendFrameworkSignal:
    framework: str
    score: int
    reasons: tuple[str, ...]
    confidence: str


@dataclass(frozen=True, slots=True)
class FrontendFrameworkDetection:
    frameworks: tuple[str, ...]
    signals: tuple[FrontendFrameworkSignal, ...]
    files_considered: int


def detect_frontend_frameworks(
    records: Iterable[InventoryRecord],
) -> FrontendFrameworkDetection:
    """Detect likely frontend frameworks from inventory path signals only."""

    evidence: dict[str, dict[str, tuple[int, str, str]]] = {
        "react": {},
        "angular": {},
    }
    files_considered = 0

    for record in records:
        files_considered += 1
        if (
            record.is_generated_guess
            or record.folder_role in {"generated", "vendor"}
            or is_generated_path(record.path)
        ):
            continue

        normalized, folders, filename, stem, extension = _path_details(record.path)
        _collect_react_evidence(
            evidence["react"], normalized, folders, filename, stem, extension
        )
        _collect_angular_evidence(
            evidence["angular"], normalized, filename, extension
        )

    signals: list[FrontendFrameworkSignal] = []
    for framework in ("react", "angular"):
        framework_evidence = evidence[framework]
        score = sum(item[0] for item in framework_evidence.values())
        if score < _DETECTION_THRESHOLD or not _has_framework_specific_evidence(
            framework, framework_evidence
        ):
            continue
        ordered = sorted(
            framework_evidence.items(),
            key=lambda item: (-item[1][0], item[0], item[1][2]),
        )
        signals.append(
            FrontendFrameworkSignal(
                framework=framework,
                score=score,
                reasons=tuple(item[1][1] for item in ordered[:MAX_FRAMEWORK_REASONS]),
                confidence=_confidence(score),
            )
        )

    signals.sort(key=lambda item: (-item.score, _FRAMEWORK_ORDER[item.framework]))
    return FrontendFrameworkDetection(
        frameworks=tuple(signal.framework for signal in signals),
        signals=tuple(signals),
        files_considered=files_considered,
    )


def _collect_react_evidence(
    evidence: dict[str, tuple[int, str, str]],
    normalized: str,
    folders: set[str],
    filename: str,
    stem: str,
    extension: str,
) -> None:
    if filename.startswith("next.config."):
        _add_evidence(evidence, "next_config", 8, "Next config filename", normalized)
    if filename.startswith("remix.config."):
        _add_evidence(evidence, "remix_config", 8, "Remix config filename", normalized)
    if filename.startswith("vite.config."):
        _add_evidence(evidence, "vite_config", 1, "Vite config filename", normalized)
    if filename in _LOCKFILES:
        _add_evidence(evidence, "lockfile", 1, "frontend lockfile name", normalized)

    if extension not in _REACT_EXTENSIONS:
        return
    _add_evidence(evidence, extension[1:], 2, f"React-like {extension} file", normalized)
    if filename in {"app.tsx", "index.tsx", "main.tsx"}:
        _add_evidence(evidence, "entrypoint", 4, "React entrypoint filename", normalized)
    if "pages" in folders:
        _add_evidence(evidence, "pages", 4, "TSX/JSX file under pages", normalized)
    if "app" in folders:
        _add_evidence(evidence, "app", 3, "TSX/JSX file under app", normalized)
    if "components" in folders:
        _add_evidence(evidence, "components", 3, "TSX/JSX file under components", normalized)
    if "hooks" in folders and stem.lower().startswith("use"):
        _add_evidence(evidence, "hook", 4, "use-prefixed file under hooks", normalized)


def _collect_angular_evidence(
    evidence: dict[str, tuple[int, str, str]],
    normalized: str,
    filename: str,
    extension: str,
) -> None:
    if "/src/app/" in f"/{normalized}":
        _add_evidence(evidence, "app_folder", 1, "Angular-like src/app path", normalized)
    if filename == "angular.json":
        _add_evidence(evidence, "angular_config", 10, "Angular config filename", normalized)
    if filename == "ng-package.json":
        _add_evidence(evidence, "ng_package", 8, "Angular package config filename", normalized)
    if filename == "workspace.json":
        _add_evidence(evidence, "workspace", 1, "workspace config filename", normalized)
    if filename == "app.module.ts":
        _add_evidence(evidence, "app_module", 6, "Angular app module filename", normalized)
    if filename == "app.routes.ts":
        _add_evidence(evidence, "app_routes", 6, "Angular app routes filename", normalized)
    if filename.endswith("-routing.module.ts"):
        _add_evidence(evidence, "routing_module", 5, "Angular routing module suffix", normalized)
    if filename.endswith(".component.ts"):
        _add_evidence(evidence, "component", 4, "Angular component TypeScript suffix", normalized)
    if filename.endswith(".component.html"):
        _add_evidence(evidence, "template", 4, "Angular component template suffix", normalized)
    if filename.endswith(".service.ts"):
        _add_evidence(evidence, "service", 2, "Angular service suffix", normalized)
    if filename.endswith(".guard.ts"):
        _add_evidence(evidence, "guard", 3, "Angular guard suffix", normalized)
    if filename.endswith(".interceptor.ts"):
        _add_evidence(evidence, "interceptor", 3, "Angular interceptor suffix", normalized)
    if extension == ".ts" and normalized.endswith("environments/environment.ts"):
        _add_evidence(evidence, "environment", 2, "Angular environment path", normalized)


def _add_evidence(
    evidence: dict[str, tuple[int, str, str]],
    category: str,
    score: int,
    description: str,
    path: str,
) -> None:
    reason = f"{description}: {path} (+{score})"
    existing = evidence.get(category)
    if existing is None or path < existing[2]:
        evidence[category] = (score, reason, path)


def _path_details(path: str) -> tuple[str, set[str], str, str, str]:
    normalized = str(path).replace("\\", "/").lower()
    parts = tuple(part for part in normalized.split("/") if part and part != ".")
    filename = parts[-1] if parts else ""
    folders = set(parts[:-1])
    if "." not in filename:
        return normalized, folders, filename, filename, ""
    stem, suffix = filename.rsplit(".", 1)
    return normalized, folders, filename, stem, f".{suffix}"


def _confidence(score: int) -> str:
    if score >= 8:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def _has_framework_specific_evidence(
    framework: str,
    evidence: dict[str, tuple[int, str, str]],
) -> bool:
    if framework == "react":
        return bool(set(evidence) - {"lockfile", "vite_config"})
    return bool(set(evidence) - {"workspace"})
