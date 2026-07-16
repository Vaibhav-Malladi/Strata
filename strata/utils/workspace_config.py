"""Workspace configuration contracts for Part Q foundation work.

Q1 is contract-only: these values describe configured repositories,
relationships, and shared contracts without discovering repositories, reading
cross-repository files, or comparing values.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


WORKSPACE_SCHEMA_VERSION = 1

REPOSITORY_ROLE_FRONTEND = "frontend"
REPOSITORY_ROLE_BACKEND = "backend"
REPOSITORY_ROLE_SHARED_LIBRARY = "shared_library"
REPOSITORY_ROLE_AUTH_SERVICE = "auth_service"
REPOSITORY_ROLE_GATEWAY = "gateway"
REPOSITORY_ROLE_WORKER = "worker"
REPOSITORY_ROLE_INFRASTRUCTURE = "infrastructure"
REPOSITORY_ROLE_UNKNOWN = "unknown"
REPOSITORY_ROLES = (
    REPOSITORY_ROLE_FRONTEND,
    REPOSITORY_ROLE_BACKEND,
    REPOSITORY_ROLE_SHARED_LIBRARY,
    REPOSITORY_ROLE_AUTH_SERVICE,
    REPOSITORY_ROLE_GATEWAY,
    REPOSITORY_ROLE_WORKER,
    REPOSITORY_ROLE_INFRASTRUCTURE,
    REPOSITORY_ROLE_UNKNOWN,
)

RELATIONSHIP_TYPE_CALLS_API = "calls_api"
RELATIONSHIP_TYPE_IMPORTS_PACKAGE = "imports_package"
RELATIONSHIP_TYPE_EMBEDS_IFRAME = "embeds_iframe"
RELATIONSHIP_TYPE_SENDS_MESSAGES_TO = "sends_messages_to"
RELATIONSHIP_TYPE_RECEIVES_MESSAGES_FROM = "receives_messages_from"
RELATIONSHIP_TYPE_SHARES_CONTRACT_WITH = "shares_contract_with"
RELATIONSHIP_TYPE_DEPENDS_ON = "depends_on"
RELATIONSHIP_TYPE_PROXIES_TO = "proxies_to"
RELATIONSHIP_TYPES = (
    RELATIONSHIP_TYPE_CALLS_API,
    RELATIONSHIP_TYPE_IMPORTS_PACKAGE,
    RELATIONSHIP_TYPE_EMBEDS_IFRAME,
    RELATIONSHIP_TYPE_SENDS_MESSAGES_TO,
    RELATIONSHIP_TYPE_RECEIVES_MESSAGES_FROM,
    RELATIONSHIP_TYPE_SHARES_CONTRACT_WITH,
    RELATIONSHIP_TYPE_DEPENDS_ON,
    RELATIONSHIP_TYPE_PROXIES_TO,
)

SHARED_CONTRACT_TYPE_AUTH_HEADER = "auth_header"
SHARED_CONTRACT_TYPE_IFRAME_URL = "iframe_url"
SHARED_CONTRACT_TYPE_API_CONSTANT = "api_constant"
SHARED_CONTRACT_TYPE_ROUTE_NAME = "route_name"
SHARED_CONTRACT_TYPE_PORT_NUMBER = "port_number"
SHARED_CONTRACT_TYPE_MESSAGE_EVENT = "message_event"
SHARED_CONTRACT_TYPE_SHARED_PACKAGE = "shared_package"
SHARED_CONTRACT_TYPE_CUSTOM = "custom"
SHARED_CONTRACT_TYPES = (
    SHARED_CONTRACT_TYPE_AUTH_HEADER,
    SHARED_CONTRACT_TYPE_IFRAME_URL,
    SHARED_CONTRACT_TYPE_API_CONSTANT,
    SHARED_CONTRACT_TYPE_ROUTE_NAME,
    SHARED_CONTRACT_TYPE_PORT_NUMBER,
    SHARED_CONTRACT_TYPE_MESSAGE_EVENT,
    SHARED_CONTRACT_TYPE_SHARED_PACKAGE,
    SHARED_CONTRACT_TYPE_CUSTOM,
)

CONTRACT_SEVERITY_INFO = "info"
CONTRACT_SEVERITY_WARNING = "warning"
CONTRACT_SEVERITY_ERROR = "error"
CONTRACT_SEVERITIES = (
    CONTRACT_SEVERITY_INFO,
    CONTRACT_SEVERITY_WARNING,
    CONTRACT_SEVERITY_ERROR,
)

CONTRACT_NORMALIZATION_EXACT = "exact"
CONTRACT_NORMALIZATION_CASE_INSENSITIVE = "case_insensitive"
CONTRACT_NORMALIZATION_TRIMMED = "trimmed"
CONTRACT_NORMALIZATION_URL = "url"
CONTRACT_NORMALIZATION_PORT = "port"
CONTRACT_NORMALIZATIONS = (
    CONTRACT_NORMALIZATION_EXACT,
    CONTRACT_NORMALIZATION_CASE_INSENSITIVE,
    CONTRACT_NORMALIZATION_TRIMMED,
    CONTRACT_NORMALIZATION_URL,
    CONTRACT_NORMALIZATION_PORT,
)

WORKSPACE_FIELD_ORDER = (
    "schema_version",
    "name",
    "repositories",
    "relationships",
    "shared_contracts",
)
REPOSITORY_FIELD_ORDER = (
    "id",
    "path",
    "role",
    "display_name",
    "known_ports",
    "known_urls",
)
RELATIONSHIP_FIELD_ORDER = (
    "source_repository_id",
    "target_repository_id",
    "relationship_type",
    "description",
)
SHARED_CONTRACT_FIELD_ORDER = (
    "name",
    "contract_type",
    "expected_value",
    "locations",
    "allowed_values",
    "severity",
    "normalization",
)
CONTRACT_LOCATION_FIELD_ORDER = (
    "repository_id",
    "path",
    "symbol",
)


class WorkspaceConfigError(ValueError):
    """Raised when workspace configuration is invalid."""


def _require_mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkspaceConfigError(f"{location}: expected an object")
    if any(not isinstance(key, str) for key in value):
        raise WorkspaceConfigError(f"{location}: field names must be strings")
    return value


def _require_keys(
    value: Mapping[str, Any],
    location: str,
    required: set[str],
    *,
    optional: set[str] | None = None,
) -> None:
    keys = set(value)
    missing = sorted(required - keys)
    if missing:
        raise WorkspaceConfigError(
            f"{location}: missing required field(s): {', '.join(missing)}"
        )
    allowed = required | (optional or set())
    unexpected = sorted(keys - allowed)
    if unexpected:
        raise WorkspaceConfigError(
            f"{location}: unexpected field(s): {', '.join(unexpected)}"
        )


def _require_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceConfigError(f"{name} must be a non-empty string")
    if value != value.strip() or "\x00" in value:
        raise WorkspaceConfigError(
            f"{name} must not contain whitespace padding or null bytes"
        )
    return value


def _normalize_optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    text = _require_nonempty_string(value, name)
    return text


def _validate_choice(value: Any, name: str, choices: tuple[str, ...]) -> str:
    text = _require_nonempty_string(value, name)
    if text not in choices:
        raise WorkspaceConfigError(f"{name} must be one of: {', '.join(choices)}")
    return text


def _validate_schema_version(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkspaceConfigError("workspace.schema_version must be an integer")
    if value != WORKSPACE_SCHEMA_VERSION:
        raise WorkspaceConfigError(
            f"workspace.schema_version must be {WORKSPACE_SCHEMA_VERSION}"
        )
    return value


def _normalize_repository_path(value: Any, name: str) -> str:
    return _normalize_relative_path(
        value,
        name,
        allow_parent=True,
        allow_current=True,
    )


def _normalize_location_path(value: Any, name: str) -> str:
    return _normalize_relative_path(
        value,
        name,
        allow_parent=False,
        allow_current=False,
    )


def _normalize_relative_path(
    value: Any,
    name: str,
    *,
    allow_parent: bool,
    allow_current: bool,
) -> str:
    text = _require_nonempty_string(value, name)
    windows_path = PureWindowsPath(text)
    posix_text = text.replace("\\", "/")
    posix_path = PurePosixPath(posix_text)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise WorkspaceConfigError(f"{name} must be relative")

    normalized = _collapse_relative_parts(posix_path.parts, allow_parent=allow_parent)
    if normalized == "." and not allow_current:
        raise WorkspaceConfigError(f"{name} must identify a file")
    if not allow_parent and ".." in PurePosixPath(normalized).parts:
        raise WorkspaceConfigError(f"{name} must not escape its repository with '..'")
    return normalized


def _collapse_relative_parts(parts: Iterable[str], *, allow_parent: bool) -> str:
    collapsed: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if collapsed and collapsed[-1] != "..":
                collapsed.pop()
            elif allow_parent:
                collapsed.append(part)
            else:
                collapsed.append(part)
            continue
        collapsed.append(part)
    if not collapsed:
        return "."
    return PurePosixPath(*collapsed).as_posix()


def _validate_known_ports(value: Any, name: str) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise WorkspaceConfigError(f"{name} must be an array of ports")
    ports: list[int] = []
    for index, port in enumerate(value):
        if isinstance(port, bool) or not isinstance(port, int):
            raise WorkspaceConfigError(f"{name}[{index}] must be an integer")
        if port < 1 or port > 65535:
            raise WorkspaceConfigError(
                f"{name}[{index}] must be between 1 and 65535"
            )
        ports.append(port)
    return tuple(sorted(set(ports)))


def _validate_known_urls(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise WorkspaceConfigError(f"{name} must be an array of strings")
    urls: list[str] = []
    for index, url in enumerate(value):
        urls.append(_require_nonempty_string(url, f"{name}[{index}]"))
    return tuple(sorted(set(urls)))


def _copy_json_scalar(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise WorkspaceConfigError(f"{name} must be a finite number")
        return value
    raise WorkspaceConfigError(f"{name} must be a JSON scalar")


def _validate_allowed_values(value: Any, name: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise WorkspaceConfigError(f"{name} must be an array of JSON scalars")

    deduplicated: dict[tuple[object, ...], Any] = {}
    for index, item in enumerate(value):
        copied = _copy_json_scalar(item, f"{name}[{index}]")
        deduplicated.setdefault(_json_sort_key(copied), copied)
    return tuple(deduplicated[key] for key in sorted(deduplicated))


def _json_sort_key(value: Any) -> tuple[object, ...]:
    if value is None:
        return ("none",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int) and not isinstance(value, bool):
        return ("int", value)
    if isinstance(value, float):
        return ("float", value)
    if isinstance(value, str):
        return ("str", value)
    raise WorkspaceConfigError("value must be JSON-ready")


def _coerce_repository(value: Any, location: str) -> "WorkspaceRepository":
    if isinstance(value, WorkspaceRepository):
        return value
    data = _require_mapping(value, location)
    _require_keys(
        data,
        location,
        {"id", "path", "role"},
        optional={"display_name", "known_ports", "known_urls"},
    )
    return WorkspaceRepository(
        id=data["id"],
        path=data["path"],
        role=data["role"],
        display_name=data.get("display_name"),
        known_ports=data.get("known_ports", ()),
        known_urls=data.get("known_urls", ()),
    )


def _coerce_relationship(value: Any, location: str) -> "WorkspaceRelationship":
    if isinstance(value, WorkspaceRelationship):
        return value
    data = _require_mapping(value, location)
    _require_keys(
        data,
        location,
        {"source_repository_id", "target_repository_id", "relationship_type"},
        optional={"description"},
    )
    return WorkspaceRelationship(
        source_repository_id=data["source_repository_id"],
        target_repository_id=data["target_repository_id"],
        relationship_type=data["relationship_type"],
        description=data.get("description"),
    )


def _coerce_contract_location(value: Any, location: str) -> "SharedContractLocation":
    if isinstance(value, SharedContractLocation):
        return value
    data = _require_mapping(value, location)
    _require_keys(
        data,
        location,
        {"repository_id", "path"},
        optional={"symbol"},
    )
    return SharedContractLocation(
        repository_id=data["repository_id"],
        path=data["path"],
        symbol=data.get("symbol"),
    )


def _coerce_shared_contract(value: Any, location: str) -> "SharedContract":
    if isinstance(value, SharedContract):
        return value
    data = _require_mapping(value, location)
    _require_keys(
        data,
        location,
        {"name", "contract_type", "expected_value", "locations"},
        optional={"allowed_values", "severity", "normalization"},
    )
    return SharedContract(
        name=data["name"],
        contract_type=data["contract_type"],
        expected_value=data["expected_value"],
        locations=data["locations"],
        allowed_values=data.get("allowed_values", ()),
        severity=data.get("severity", CONTRACT_SEVERITY_WARNING),
        normalization=data.get("normalization", CONTRACT_NORMALIZATION_EXACT),
    )


def _validate_iterable(value: Any, name: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise WorkspaceConfigError(f"{name} must be an array")
    return tuple(value)


def _repository_sort_key(repository: "WorkspaceRepository") -> tuple[object, ...]:
    return (
        repository.id,
        repository.path,
        REPOSITORY_ROLES.index(repository.role),
        repository.display_name or "",
        repository.known_ports,
        repository.known_urls,
    )


def _relationship_sort_key(relationship: "WorkspaceRelationship") -> tuple[object, ...]:
    return (
        relationship.source_repository_id,
        relationship.target_repository_id,
        RELATIONSHIP_TYPES.index(relationship.relationship_type),
        relationship.description or "",
    )


def _location_sort_key(location: "SharedContractLocation") -> tuple[object, ...]:
    return (
        location.repository_id,
        location.path,
        location.symbol or "",
    )


def _shared_contract_sort_key(contract: "SharedContract") -> tuple[object, ...]:
    return (
        contract.name,
        SHARED_CONTRACT_TYPES.index(contract.contract_type),
        _json_sort_key(contract.expected_value),
        tuple(_location_sort_key(location) for location in contract.locations),
        tuple(_json_sort_key(value) for value in contract.allowed_values),
        CONTRACT_SEVERITIES.index(contract.severity),
        CONTRACT_NORMALIZATIONS.index(contract.normalization),
    )


@dataclass(frozen=True, slots=True)
class WorkspaceRepository:
    """One configured repository in a workspace."""

    id: str
    path: str
    role: str
    display_name: str | None = None
    known_ports: tuple[int, ...] = ()
    known_urls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_nonempty_string(self.id, "repository.id"))
        object.__setattr__(
            self,
            "path",
            _normalize_repository_path(self.path, "repository.path"),
        )
        object.__setattr__(
            self,
            "role",
            _validate_choice(self.role, "repository.role", REPOSITORY_ROLES),
        )
        object.__setattr__(
            self,
            "display_name",
            _normalize_optional_string(self.display_name, "repository.display_name"),
        )
        object.__setattr__(
            self,
            "known_ports",
            _validate_known_ports(self.known_ports, "repository.known_ports"),
        )
        object.__setattr__(
            self,
            "known_urls",
            _validate_known_urls(self.known_urls, "repository.known_urls"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "role": self.role,
            "display_name": self.display_name,
            "known_ports": list(self.known_ports),
            "known_urls": list(self.known_urls),
        }


@dataclass(frozen=True, slots=True)
class WorkspaceRelationship:
    """One explicit configured relationship between two repositories."""

    source_repository_id: str
    target_repository_id: str
    relationship_type: str
    description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_repository_id",
            _require_nonempty_string(
                self.source_repository_id,
                "relationship.source_repository_id",
            ),
        )
        object.__setattr__(
            self,
            "target_repository_id",
            _require_nonempty_string(
                self.target_repository_id,
                "relationship.target_repository_id",
            ),
        )
        if self.source_repository_id == self.target_repository_id:
            raise WorkspaceConfigError("relationship source and target must differ")
        object.__setattr__(
            self,
            "relationship_type",
            _validate_choice(
                self.relationship_type,
                "relationship.relationship_type",
                RELATIONSHIP_TYPES,
            ),
        )
        object.__setattr__(
            self,
            "description",
            _normalize_optional_string(self.description, "relationship.description"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_repository_id": self.source_repository_id,
            "target_repository_id": self.target_repository_id,
            "relationship_type": self.relationship_type,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class SharedContractLocation:
    """One configured location for a shared contract value."""

    repository_id: str
    path: str
    symbol: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "repository_id",
            _require_nonempty_string(self.repository_id, "location.repository_id"),
        )
        object.__setattr__(
            self,
            "path",
            _normalize_location_path(self.path, "location.path"),
        )
        object.__setattr__(
            self,
            "symbol",
            _normalize_optional_string(self.symbol, "location.symbol"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "path": self.path,
            "symbol": self.symbol,
        }


@dataclass(frozen=True, slots=True)
class SharedContract:
    """One configured value expected to stay consistent across repositories."""

    name: str
    contract_type: str
    expected_value: Any
    locations: tuple[SharedContractLocation, ...]
    allowed_values: tuple[Any, ...] = ()
    severity: str = CONTRACT_SEVERITY_WARNING
    normalization: str = CONTRACT_NORMALIZATION_EXACT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            _require_nonempty_string(self.name, "shared_contract.name"),
        )
        object.__setattr__(
            self,
            "contract_type",
            _validate_choice(
                self.contract_type,
                "shared_contract.contract_type",
                SHARED_CONTRACT_TYPES,
            ),
        )
        object.__setattr__(
            self,
            "expected_value",
            _copy_json_scalar(self.expected_value, "shared_contract.expected_value"),
        )
        locations = tuple(
            _coerce_contract_location(item, f"shared_contract.locations[{index}]")
            for index, item in enumerate(_validate_iterable(self.locations, "shared_contract.locations"))
        )
        if not locations:
            raise WorkspaceConfigError("shared_contract.locations must not be empty")
        object.__setattr__(
            self,
            "locations",
            tuple(sorted(set(locations), key=_location_sort_key)),
        )
        object.__setattr__(
            self,
            "allowed_values",
            _validate_allowed_values(
                self.allowed_values,
                "shared_contract.allowed_values",
            ),
        )
        object.__setattr__(
            self,
            "severity",
            _validate_choice(
                self.severity,
                "shared_contract.severity",
                CONTRACT_SEVERITIES,
            ),
        )
        object.__setattr__(
            self,
            "normalization",
            _validate_choice(
                self.normalization,
                "shared_contract.normalization",
                CONTRACT_NORMALIZATIONS,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "contract_type": self.contract_type,
            "expected_value": self.expected_value,
            "locations": [location.to_dict() for location in self.locations],
            "allowed_values": list(self.allowed_values),
            "severity": self.severity,
            "normalization": self.normalization,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceConfig:
    """Top-level immutable workspace configuration contract."""

    schema_version: int
    name: str
    repositories: tuple[WorkspaceRepository, ...]
    relationships: tuple[WorkspaceRelationship, ...] = ()
    shared_contracts: tuple[SharedContract, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _validate_schema_version(self.schema_version),
        )
        object.__setattr__(self, "name", _require_nonempty_string(self.name, "workspace.name"))

        repositories = tuple(
            _coerce_repository(item, f"workspace.repositories[{index}]")
            for index, item in enumerate(_validate_iterable(self.repositories, "workspace.repositories"))
        )
        duplicate_repository_id = _first_duplicate(repository.id for repository in repositories)
        if duplicate_repository_id is not None:
            raise WorkspaceConfigError(
                f"workspace.repositories contains duplicate repository id: {duplicate_repository_id}"
            )
        repository_ids = {repository.id for repository in repositories}
        object.__setattr__(
            self,
            "repositories",
            tuple(sorted(repositories, key=_repository_sort_key)),
        )

        relationships = tuple(
            _coerce_relationship(item, f"workspace.relationships[{index}]")
            for index, item in enumerate(_validate_iterable(self.relationships, "workspace.relationships"))
        )
        for relationship in relationships:
            _require_known_repository_id(
                relationship.source_repository_id,
                repository_ids,
                "relationship.source_repository_id",
            )
            _require_known_repository_id(
                relationship.target_repository_id,
                repository_ids,
                "relationship.target_repository_id",
            )
        object.__setattr__(
            self,
            "relationships",
            tuple(sorted(set(relationships), key=_relationship_sort_key)),
        )

        shared_contracts = tuple(
            _coerce_shared_contract(item, f"workspace.shared_contracts[{index}]")
            for index, item in enumerate(_validate_iterable(self.shared_contracts, "workspace.shared_contracts"))
        )
        for contract in shared_contracts:
            for location in contract.locations:
                _require_known_repository_id(
                    location.repository_id,
                    repository_ids,
                    "shared_contract.location.repository_id",
                )
        object.__setattr__(
            self,
            "shared_contracts",
            tuple(sorted(set(shared_contracts), key=_shared_contract_sort_key)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "repositories": [repository.to_dict() for repository in self.repositories],
            "relationships": [relationship.to_dict() for relationship in self.relationships],
            "shared_contracts": [contract.to_dict() for contract in self.shared_contracts],
        }


def _first_duplicate(values: Iterable[str]) -> str | None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
    return None


def _require_known_repository_id(
    repository_id: str,
    repository_ids: set[str],
    name: str,
) -> None:
    if repository_id not in repository_ids:
        raise WorkspaceConfigError(
            f"{name} references unknown repository id: {repository_id}"
        )


def create_workspace_config(**values: Any) -> WorkspaceConfig:
    """Create and validate a workspace configuration contract value."""

    return WorkspaceConfig(**values)


def workspace_config_to_dict(workspace: WorkspaceConfig) -> dict[str, Any]:
    """Return the stable JSON-ready workspace configuration representation."""

    if not isinstance(workspace, WorkspaceConfig):
        raise TypeError("workspace must be a WorkspaceConfig")
    return workspace.to_dict()


def validate_workspace_config(payload: Any) -> dict[str, Any]:
    """Validate a decoded workspace config object and return a normalized dict."""

    data = _require_mapping(payload, "workspace")
    _require_keys(
        data,
        "workspace",
        {"schema_version", "name", "repositories"},
        optional={"relationships", "shared_contracts"},
    )
    workspace = WorkspaceConfig(
        schema_version=data["schema_version"],
        name=data["name"],
        repositories=data["repositories"],
        relationships=data.get("relationships", ()),
        shared_contracts=data.get("shared_contracts", ()),
    )
    return workspace.to_dict()
