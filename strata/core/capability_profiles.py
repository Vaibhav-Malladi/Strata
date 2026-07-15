from dataclasses import dataclass, replace
from types import MappingProxyType


CAPABILITY_TIER_UNKNOWN = "unknown"
CAPABILITY_TIER_WEAK = "weak"
CAPABILITY_TIER_MEDIUM = "medium"
CAPABILITY_TIER_STRONG = "strong"
CAPABILITY_TIERS = (
    CAPABILITY_TIER_UNKNOWN,
    CAPABILITY_TIER_WEAK,
    CAPABILITY_TIER_MEDIUM,
    CAPABILITY_TIER_STRONG,
)

CONTEXT_WINDOW_CLASS_SMALL = "small"
CONTEXT_WINDOW_CLASS_MEDIUM = "medium"
CONTEXT_WINDOW_CLASS_LARGE = "large"
CONTEXT_WINDOW_CLASS_UNKNOWN = "unknown"
CONTEXT_WINDOW_CLASSES = (
    CONTEXT_WINDOW_CLASS_SMALL,
    CONTEXT_WINDOW_CLASS_MEDIUM,
    CONTEXT_WINDOW_CLASS_LARGE,
    CONTEXT_WINDOW_CLASS_UNKNOWN,
)

CAPABILITY_RELIABILITY_LOW = "low"
CAPABILITY_RELIABILITY_MEDIUM = "medium"
CAPABILITY_RELIABILITY_HIGH = "high"
CAPABILITY_RELIABILITY_UNKNOWN = "unknown"
CAPABILITY_RELIABILITY_VALUES = (
    CAPABILITY_RELIABILITY_LOW,
    CAPABILITY_RELIABILITY_MEDIUM,
    CAPABILITY_RELIABILITY_HIGH,
    CAPABILITY_RELIABILITY_UNKNOWN,
)

CONTEXT_VARIANT_COMPACT = "compact"
CONTEXT_VARIANT_BALANCED = "balanced"
CONTEXT_VARIANT_EXPANDED = "expanded"
CONTEXT_VARIANTS = (
    CONTEXT_VARIANT_COMPACT,
    CONTEXT_VARIANT_BALANCED,
    CONTEXT_VARIANT_EXPANDED,
)

MAX_RECOMMENDED_FILES_LIMIT = 40

CAPABILITY_PROFILE_FIELD_ORDER = (
    "tier",
    "context_window_class",
    "instruction_adherence",
    "diff_reliability",
    "structured_output_reliability",
    "multi_file_reasoning",
    "needs_explicit_steps",
    "needs_diff_example",
    "preferred_context_variant",
    "max_recommended_files",
)


def _validate_reliability(value: str, field_name: str) -> str:
    return _validate_choice(value, field_name, CAPABILITY_RELIABILITY_VALUES)


def _validate_choice(value: str, field_name: str, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string.")
    if value not in choices:
        raise ValueError(f"{field_name} must be one of: {', '.join(choices)}.")
    return value


def _validate_bool(value: bool, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean.")
    return value


def _validate_max_recommended_files(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("max_recommended_files must be an integer.")
    if value <= 0:
        raise ValueError("max_recommended_files must be a positive integer.")
    if value > MAX_RECOMMENDED_FILES_LIMIT:
        raise ValueError(
            f"max_recommended_files must be at most {MAX_RECOMMENDED_FILES_LIMIT}."
        )
    return value


@dataclass(frozen=True)
class CapabilityProfile:
    tier: str
    context_window_class: str
    instruction_adherence: str
    diff_reliability: str
    structured_output_reliability: str
    multi_file_reasoning: str
    needs_explicit_steps: bool
    needs_diff_example: bool
    preferred_context_variant: str
    max_recommended_files: int

    def __post_init__(self) -> None:
        _validate_choice(self.tier, "tier", CAPABILITY_TIERS)
        _validate_choice(
            self.context_window_class,
            "context_window_class",
            CONTEXT_WINDOW_CLASSES,
        )
        _validate_reliability(self.instruction_adherence, "instruction_adherence")
        _validate_reliability(self.diff_reliability, "diff_reliability")
        _validate_reliability(
            self.structured_output_reliability,
            "structured_output_reliability",
        )
        _validate_reliability(self.multi_file_reasoning, "multi_file_reasoning")
        _validate_bool(self.needs_explicit_steps, "needs_explicit_steps")
        _validate_bool(self.needs_diff_example, "needs_diff_example")
        _validate_choice(
            self.preferred_context_variant,
            "preferred_context_variant",
            CONTEXT_VARIANTS,
        )
        _validate_max_recommended_files(self.max_recommended_files)

    def to_dict(self) -> dict[str, object]:
        return {
            "tier": self.tier,
            "context_window_class": self.context_window_class,
            "instruction_adherence": self.instruction_adherence,
            "diff_reliability": self.diff_reliability,
            "structured_output_reliability": self.structured_output_reliability,
            "multi_file_reasoning": self.multi_file_reasoning,
            "needs_explicit_steps": self.needs_explicit_steps,
            "needs_diff_example": self.needs_diff_example,
            "preferred_context_variant": self.preferred_context_variant,
            "max_recommended_files": self.max_recommended_files,
        }


WEAK_CAPABILITY_PROFILE = CapabilityProfile(
    tier=CAPABILITY_TIER_WEAK,
    context_window_class=CONTEXT_WINDOW_CLASS_SMALL,
    instruction_adherence=CAPABILITY_RELIABILITY_LOW,
    diff_reliability=CAPABILITY_RELIABILITY_LOW,
    structured_output_reliability=CAPABILITY_RELIABILITY_LOW,
    multi_file_reasoning=CAPABILITY_RELIABILITY_LOW,
    needs_explicit_steps=True,
    needs_diff_example=True,
    preferred_context_variant=CONTEXT_VARIANT_COMPACT,
    max_recommended_files=8,
)

MEDIUM_CAPABILITY_PROFILE = CapabilityProfile(
    tier=CAPABILITY_TIER_MEDIUM,
    context_window_class=CONTEXT_WINDOW_CLASS_MEDIUM,
    instruction_adherence=CAPABILITY_RELIABILITY_MEDIUM,
    diff_reliability=CAPABILITY_RELIABILITY_MEDIUM,
    structured_output_reliability=CAPABILITY_RELIABILITY_MEDIUM,
    multi_file_reasoning=CAPABILITY_RELIABILITY_MEDIUM,
    needs_explicit_steps=False,
    needs_diff_example=False,
    preferred_context_variant=CONTEXT_VARIANT_BALANCED,
    max_recommended_files=16,
)

STRONG_CAPABILITY_PROFILE = CapabilityProfile(
    tier=CAPABILITY_TIER_STRONG,
    context_window_class=CONTEXT_WINDOW_CLASS_LARGE,
    instruction_adherence=CAPABILITY_RELIABILITY_HIGH,
    diff_reliability=CAPABILITY_RELIABILITY_HIGH,
    structured_output_reliability=CAPABILITY_RELIABILITY_HIGH,
    multi_file_reasoning=CAPABILITY_RELIABILITY_HIGH,
    needs_explicit_steps=False,
    needs_diff_example=False,
    preferred_context_variant=CONTEXT_VARIANT_EXPANDED,
    max_recommended_files=30,
)

CONSERVATIVE_UNKNOWN_PROFILE = CapabilityProfile(
    tier=CAPABILITY_TIER_UNKNOWN,
    context_window_class=CONTEXT_WINDOW_CLASS_UNKNOWN,
    instruction_adherence=CAPABILITY_RELIABILITY_UNKNOWN,
    diff_reliability=CAPABILITY_RELIABILITY_UNKNOWN,
    structured_output_reliability=CAPABILITY_RELIABILITY_UNKNOWN,
    multi_file_reasoning=CAPABILITY_RELIABILITY_UNKNOWN,
    needs_explicit_steps=True,
    needs_diff_example=True,
    preferred_context_variant=CONTEXT_VARIANT_BALANCED,
    max_recommended_files=12,
)

BUILT_IN_CAPABILITY_PROFILES = MappingProxyType(
    {
        CAPABILITY_TIER_UNKNOWN: CONSERVATIVE_UNKNOWN_PROFILE,
        CAPABILITY_TIER_WEAK: WEAK_CAPABILITY_PROFILE,
        CAPABILITY_TIER_MEDIUM: MEDIUM_CAPABILITY_PROFILE,
        CAPABILITY_TIER_STRONG: STRONG_CAPABILITY_PROFILE,
    }
)


def get_capability_profile(tier: str) -> CapabilityProfile:
    """Return the built-in capability profile for a stable internal tier."""

    tier = _validate_choice(tier, "tier", CAPABILITY_TIERS)
    return BUILT_IN_CAPABILITY_PROFILES[tier]


def get_conservative_unknown_profile() -> CapabilityProfile:
    """Return the conservative fallback profile for unknown model capability."""

    return CONSERVATIVE_UNKNOWN_PROFILE


def with_capability_overrides(
    profile: CapabilityProfile,
    *,
    preferred_context_variant: str | None = None,
    max_recommended_files: int | None = None,
) -> CapabilityProfile:
    """Return a new profile with the small O1 override surface applied."""

    if not isinstance(profile, CapabilityProfile):
        raise ValueError("profile must be a CapabilityProfile.")

    values: dict[str, object] = {}
    if preferred_context_variant is not None:
        values["preferred_context_variant"] = _validate_choice(
            preferred_context_variant,
            "preferred_context_variant",
            CONTEXT_VARIANTS,
        )
    if max_recommended_files is not None:
        values["max_recommended_files"] = _validate_max_recommended_files(
            max_recommended_files
        )

    return replace(profile, **values)
