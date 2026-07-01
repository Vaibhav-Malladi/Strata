import re
from dataclasses import dataclass
from typing import Iterable

from strata.core.inventory import InventoryRecord


_STOPWORDS = {
    "a",
    "add",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "bug",
    "by",
    "change",
    "create",
    "fix",
    "for",
    "from",
    "implement",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "refactor",
    "remove",
    "the",
    "to",
    "update",
    "with",
}

_ROLE_WORDS = {
    "api",
    "client",
    "component",
    "controller",
    "hook",
    "model",
    "page",
    "route",
    "routes",
    "schema",
    "service",
    "spec",
    "store",
    "test",
    "view",
}

_TEST_TASK_WORDS = {"spec", "specs", "test", "testing", "tests"}

_LANGUAGE_ALIASES = {
    "csharp": {"csharp", "cs"},
    "cpp": {"cpp"},
    "javascript": {"javascript", "js", "jsx"},
    "kotlin": {"kotlin", "kt", "kts"},
    "markdown": {"markdown", "md"},
    "powershell": {"powershell", "ps1"},
    "python": {"python", "py"},
    "typescript": {"typescript", "ts", "tsx"},
    "yaml": {"yaml", "yml"},
}

_FILENAME_MATCH_SCORE = 6
_FOLDER_MATCH_SCORE = 3
_ROLE_MATCH_SCORE = 2
_ROLE_SIGNAL_SCORE = 1
_FOLDER_ROLE_MATCH_SCORE = 3
_SOURCE_FOLDER_SCORE = 1
_LANGUAGE_MATCH_SCORE = 2
_EXTENSION_MATCH_SCORE = 2
_TEST_PENALTY = -12
_TEST_TASK_BOOST = 8
_GENERATED_PENALTY = -100
DEFAULT_SHORTLIST_LIMIT = 300


@dataclass(frozen=True, slots=True)
class CandidateScore:
    path: str
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateShortlist:
    candidates: tuple[CandidateScore, ...]
    files_considered: int
    cap: int
    truncated: bool

    @property
    def candidates_returned(self) -> int:
        return len(self.candidates)


@dataclass(frozen=True, slots=True)
class CandidateValue:
    path: str
    cheap_score: int
    analysis_cost: int
    value_score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    candidates: tuple[CandidateValue, ...]
    files_considered: int
    cap: int
    truncated: bool

    @property
    def candidates_returned(self) -> int:
        return len(self.candidates)


def normalize_task_tokens(task: str) -> tuple[str, ...]:
    """Return unique, useful lowercase task words in their original order."""

    words = re.findall(r"[a-z0-9]+", task.lower())
    return tuple(dict.fromkeys(word for word in words if word not in _STOPWORDS))


def score_candidate(record: InventoryRecord, task: str) -> CandidateScore:
    """Score one inventory record without touching the filesystem."""

    task_tokens = set(normalize_task_tokens(task))
    stem_tokens, folder_tokens, path_tokens = _path_signals(record.path)
    score = 0
    reasons: list[str] = []

    for token in sorted(task_tokens & stem_tokens):
        score += _FILENAME_MATCH_SCORE
        reasons.append(f"filename matches task keyword '{token}' (+{_FILENAME_MATCH_SCORE})")

    for token in sorted((task_tokens & folder_tokens) - stem_tokens):
        score += _FOLDER_MATCH_SCORE
        reasons.append(f"folder matches task keyword '{token}' (+{_FOLDER_MATCH_SCORE})")

    role_words = path_tokens & _ROLE_WORDS
    for role in sorted(role_words - _TEST_TASK_WORDS):
        if role in task_tokens:
            score += _ROLE_MATCH_SCORE
            reasons.append(f"relevant path role '{role}' (+{_ROLE_MATCH_SCORE})")
        else:
            score += _ROLE_SIGNAL_SCORE
            reasons.append(f"path role signal '{role}' (+{_ROLE_SIGNAL_SCORE})")

    if record.folder_role in task_tokens and record.folder_role != "test":
        score += _FOLDER_ROLE_MATCH_SCORE
        reasons.append(
            f"folder role '{record.folder_role}' matches task (+{_FOLDER_ROLE_MATCH_SCORE})"
        )
    elif record.folder_role == "source":
        score += _SOURCE_FOLDER_SCORE
        reasons.append(f"source folder (+{_SOURCE_FOLDER_SCORE})")

    language_aliases = _LANGUAGE_ALIASES.get(
        record.language_guess or "",
        {record.language_guess} if record.language_guess else set(),
    )
    if task_tokens & language_aliases:
        score += _LANGUAGE_MATCH_SCORE
        reasons.append(
            f"language '{record.language_guess}' matches task (+{_LANGUAGE_MATCH_SCORE})"
        )

    extension = record.extension.lower().lstrip(".")
    if extension and extension in task_tokens:
        score += _EXTENSION_MATCH_SCORE
        reasons.append(f"extension '.{extension}' matches task (+{_EXTENSION_MATCH_SCORE})")

    asks_for_tests = bool(task_tokens & _TEST_TASK_WORDS)
    if record.is_test:
        if asks_for_tests:
            score += _TEST_TASK_BOOST
            reasons.append(f"task asks for tests (+{_TEST_TASK_BOOST})")
        else:
            score += _TEST_PENALTY
            reasons.append(f"test file for implementation task ({_TEST_PENALTY})")

    if record.is_generated_guess or record.folder_role in {"generated", "vendor"}:
        score += _GENERATED_PENALTY
        reasons.append(f"generated or vendor path ({_GENERATED_PENALTY})")

    return CandidateScore(path=record.path, score=score, reasons=tuple(reasons))


def rank_candidates(
    records: Iterable[InventoryRecord],
    task: str,
) -> list[CandidateScore]:
    """Score records and return the strongest cheap candidates first."""

    candidates = [score_candidate(record, task) for record in records]
    return sorted(candidates, key=lambda candidate: (-candidate.score, candidate.path.lower()))


def shortlist_candidates(
    records: Iterable[InventoryRecord],
    task: str,
    limit: int = DEFAULT_SHORTLIST_LIMIT,
) -> CandidateShortlist:
    """Return a bounded summary of the strongest cheap candidates."""

    _validate_limit(limit)

    ranked = rank_candidates(records, task)
    return CandidateShortlist(
        candidates=tuple(ranked[:limit]),
        files_considered=len(ranked),
        cap=limit,
        truncated=len(ranked) > limit,
    )


def estimate_analysis_cost(record: InventoryRecord) -> int:
    """Estimate relative analysis cost from inventory metadata only."""

    cost, _ = _analysis_cost(record)
    return cost


def compute_value_score(cheap_score: int, analysis_cost: int) -> float:
    """Combine relevance and cost without rewarding costly negative scores."""

    if analysis_cost <= 0:
        raise ValueError("analysis_cost must be greater than zero")
    if cheap_score >= 0:
        return round(cheap_score / analysis_cost, 6)
    return float(cheap_score * analysis_cost)


def score_candidate_value(record: InventoryRecord, task: str) -> CandidateValue:
    """Build an explainable value score without touching the filesystem."""

    cheap = score_candidate(record, task)
    analysis_cost, cost_reasons = _analysis_cost(record)
    value_score = compute_value_score(cheap.score, analysis_cost)
    value_reason = (
        f"value score {value_score:g} from cheap score {cheap.score} "
        f"and analysis cost {analysis_cost}"
    )
    return CandidateValue(
        path=record.path,
        cheap_score=cheap.score,
        analysis_cost=analysis_cost,
        value_score=value_score,
        reasons=cheap.reasons + cost_reasons + (value_reason,),
    )


def rank_candidates_by_value(
    records: Iterable[InventoryRecord],
    task: str,
    limit: int = DEFAULT_SHORTLIST_LIMIT,
) -> list[CandidateValue]:
    """Return the best usefulness-per-cost candidates first."""

    _validate_limit(limit)
    candidates = [score_candidate_value(record, task) for record in records]
    candidates.sort(
        key=lambda candidate: (
            -candidate.value_score,
            -candidate.cheap_score,
            candidate.analysis_cost,
            candidate.path.lower(),
            candidate.path,
        )
    )
    return candidates[:limit]


def select_candidates(
    records: Iterable[InventoryRecord],
    task: str,
    limit: int = DEFAULT_SHORTLIST_LIMIT,
) -> CandidateSelection:
    """Turn inventory records into a bounded, value-ranked selection."""

    _validate_limit(limit)
    inventory = list(records)
    candidates = rank_candidates_by_value(inventory, task, limit=limit)
    return CandidateSelection(
        candidates=tuple(candidates),
        files_considered=len(inventory),
        cap=limit,
        truncated=len(inventory) > limit,
    )


def _analysis_cost(record: InventoryRecord) -> tuple[int, tuple[str, ...]]:
    size = max(record.size, 0)
    if size <= 16 * 1024:
        cost = 1
        size_reason = "size at most 16 KiB (cost 1)"
    elif size <= 128 * 1024:
        cost = 2
        size_reason = "size at most 128 KiB (cost 2)"
    elif size <= 512 * 1024:
        cost = 4
        size_reason = "size at most 512 KiB (cost 4)"
    elif size <= 2 * 1024 * 1024:
        cost = 8
        size_reason = "size at most 2 MiB (cost 8)"
    else:
        cost = 16
        size_reason = "size above 2 MiB (cost 16)"

    reasons = [size_reason]
    if record.is_test:
        cost += 1
        reasons.append("test file (+1 cost)")
    if record.is_generated_guess or record.folder_role in {"generated", "vendor"}:
        cost += 20
        reasons.append("generated or vendor path (+20 cost)")
    return cost, tuple(reasons)


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")


def _path_signals(path: str) -> tuple[set[str], set[str], set[str]]:
    normalized = path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    filename = parts[-1] if parts else ""
    stem = filename.rsplit(".", 1)[0]
    stem_tokens = set(_name_tokens(stem))
    folder_tokens = {
        token
        for folder in parts[:-1]
        for token in _name_tokens(folder)
    }
    return stem_tokens, folder_tokens, stem_tokens | folder_tokens


def _name_tokens(value: str) -> tuple[str, ...]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return tuple(re.findall(r"[a-z0-9]+", separated.lower()))
