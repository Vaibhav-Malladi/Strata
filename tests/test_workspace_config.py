import json
import tempfile
from pathlib import Path

import strata.core.user_settings as user_settings
import strata.utils.config as workflow_config
import strata.utils.workspace_config as workspace_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _repository(repository_id: str, **overrides):
    values = {
        "id": repository_id,
        "path": f"../{repository_id}",
        "role": "unknown",
    }
    values.update(overrides)
    return values


def _minimal_workspace(**overrides):
    values = {
        "schema_version": 1,
        "name": "example-application",
        "repositories": [],
    }
    values.update(overrides)
    return values


def _complete_workspace(**overrides):
    values = _minimal_workspace(
        repositories=[
            _repository(
                "backend",
                path="..\\backend\\.\\service",
                role="backend",
                display_name="Backend API",
                known_ports=[8080, 8080, 9000],
                known_urls=[
                    "http://localhost:9000",
                    "http://localhost:8080",
                    "http://localhost:8080",
                ],
            ),
            _repository(
                "frontend",
                path="../apps/../frontend",
                role="frontend",
                known_ports=[4200],
                known_urls=["http://localhost:4200"],
            ),
        ],
        relationships=[
            {
                "source_repository_id": "frontend",
                "target_repository_id": "backend",
                "relationship_type": "calls_api",
            },
            {
                "source_repository_id": "frontend",
                "target_repository_id": "backend",
                "relationship_type": "calls_api",
            },
        ],
        shared_contracts=[
            {
                "name": "api-port",
                "contract_type": "port_number",
                "expected_value": 8080,
                "allowed_values": ["8080", 8080],
                "severity": "error",
                "normalization": "port",
                "locations": [
                    {
                        "repository_id": "backend",
                        "path": "config\\server.json",
                        "symbol": "PORT",
                    },
                    {
                        "repository_id": "frontend",
                        "path": "src/../src/environments/environment.ts",
                        "symbol": "apiPort",
                    },
                    {
                        "repository_id": "backend",
                        "path": "config/server.json",
                        "symbol": "PORT",
                    },
                ],
            }
        ],
    )
    values.update(overrides)
    return values


def _expect_error(function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except ValueError as error:
        assert contains in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_minimal_valid_workspace_is_json_ready():
    payload = workspace_config.validate_workspace_config(_minimal_workspace())

    assert list(payload) == list(workspace_config.WORKSPACE_FIELD_ORDER)
    assert payload == {
        "schema_version": 1,
        "name": "example-application",
        "repositories": [],
        "relationships": [],
        "shared_contracts": [],
    }
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_unsupported_workspace_schema_version_is_rejected():
    _expect_error(
        workspace_config.validate_workspace_config,
        _minimal_workspace(schema_version=2),
        contains="schema_version",
    )


def test_complete_workspace_serialization_is_deterministic():
    payload = workspace_config.validate_workspace_config(_complete_workspace())

    assert [repository["id"] for repository in payload["repositories"]] == [
        "backend",
        "frontend",
    ]
    assert payload["repositories"][0]["path"] == "../backend/service"
    assert payload["repositories"][0]["known_ports"] == [8080, 9000]
    assert payload["repositories"][0]["known_urls"] == [
        "http://localhost:8080",
        "http://localhost:9000",
    ]
    assert payload["repositories"][1]["path"] == "../frontend"
    assert payload["relationships"] == [
        {
            "source_repository_id": "frontend",
            "target_repository_id": "backend",
            "relationship_type": "calls_api",
            "description": None,
        }
    ]
    contract = payload["shared_contracts"][0]
    assert list(contract) == list(workspace_config.SHARED_CONTRACT_FIELD_ORDER)
    assert contract["expected_value"] == 8080
    assert contract["allowed_values"] == [8080, "8080"]
    assert contract["locations"] == [
        {
            "repository_id": "backend",
            "path": "config/server.json",
            "symbol": "PORT",
        },
        {
            "repository_id": "frontend",
            "path": "src/environments/environment.ts",
            "symbol": "apiPort",
        },
    ]
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_config_round_trip_preserves_unrelated_values_and_profile_overrides():
    with tempfile.TemporaryDirectory() as temp_dir:
        settings = user_settings.update_user_settings(
            user_settings.default_user_settings(),
            {"profile_overrides": {"max_recommended_files": 4}},
        )
        saved = workflow_config.save_config(
            {
                "mode": "hybrid",
                "agent": "codex",
                "command": "py fake_ai.py",
                "user_settings": settings,
                "workspace": _complete_workspace(),
            },
            temp_dir,
        )

        loaded = workflow_config.load_config(temp_dir)
        payload = json.loads(saved.read_text(encoding="utf-8"))

        assert loaded["mode"] == "hybrid"
        assert loaded["agent"] == "codex"
        assert loaded["command"] == "py fake_ai.py"
        assert loaded["user_settings"]["profile_overrides"] == {
            "max_recommended_files": 4
        }
        assert loaded["workspace"] == workflow_config.validate_config(payload)["workspace"]
        assert payload["workspace"] == loaded["workspace"]


def test_repository_path_normalization_is_deterministic():
    payload = workspace_config.validate_workspace_config(
        _minimal_workspace(
            repositories=[
                _repository("frontend", path="..\\apps\\.\\frontend\\src\\.."),
                _repository("current", path="."),
            ]
        )
    )

    assert [repository["path"] for repository in payload["repositories"]] == [
        ".",
        "../apps/frontend",
    ]


def test_supported_repository_roles_are_bounded():
    for role in workspace_config.REPOSITORY_ROLES:
        payload = workspace_config.WorkspaceRepository(
            id=f"repo-{role}",
            path=f"../{role}",
            role=role,
        ).to_dict()

        assert payload["role"] == role


def test_unsupported_repository_role_is_rejected():
    _expect_error(
        workspace_config.validate_workspace_config,
        _minimal_workspace(repositories=[_repository("frontend", role="mobile")]),
        contains="repository.role",
    )


def test_valid_and_invalid_ports_are_validated():
    repository = workspace_config.WorkspaceRepository(
        id="backend",
        path="../backend",
        role="backend",
        known_ports=[65535, 1, 8080, 8080],
    )

    assert repository.known_ports == (1, 8080, 65535)
    for port in (0, 65536, "8080", True):
        _expect_error(
            workspace_config.WorkspaceRepository,
            id="backend",
            path="../backend",
            role="backend",
            known_ports=[port],
            contains="known_ports",
        )


def test_supported_relationship_types_are_bounded():
    for relationship_type in workspace_config.RELATIONSHIP_TYPES:
        relationship = workspace_config.WorkspaceRelationship(
            source_repository_id="frontend",
            target_repository_id="backend",
            relationship_type=relationship_type,
        )

        assert relationship.relationship_type == relationship_type


def test_unsupported_relationship_type_is_rejected():
    _expect_error(
        workspace_config.WorkspaceRelationship,
        source_repository_id="frontend",
        target_repository_id="backend",
        relationship_type="syncs_database",
        contains="relationship.relationship_type",
    )


def test_self_relationship_is_rejected():
    _expect_error(
        workspace_config.WorkspaceRelationship,
        source_repository_id="frontend",
        target_repository_id="frontend",
        relationship_type="depends_on",
        contains="source and target",
    )


def test_unknown_repository_relationship_references_are_rejected():
    _expect_error(
        workspace_config.validate_workspace_config,
        _minimal_workspace(
            repositories=[_repository("frontend", role="frontend")],
            relationships=[
                {
                    "source_repository_id": "frontend",
                    "target_repository_id": "backend",
                    "relationship_type": "calls_api",
                }
            ],
        ),
        contains="unknown repository id",
    )


def test_duplicate_repository_ids_are_rejected():
    _expect_error(
        workspace_config.validate_workspace_config,
        _minimal_workspace(
            repositories=[
                _repository("frontend", path="../frontend"),
                _repository("frontend", path="../frontend-copy"),
            ]
        ),
        contains="duplicate repository id",
    )


def test_shared_contract_with_multiple_locations_is_supported():
    payload = workspace_config.validate_workspace_config(_complete_workspace())
    contract = payload["shared_contracts"][0]

    assert contract["name"] == "api-port"
    assert len(contract["locations"]) == 2


def test_shared_contract_missing_locations_is_rejected():
    _expect_error(
        workspace_config.validate_workspace_config,
        _complete_workspace(
            shared_contracts=[
                {
                    "name": "authorization-header",
                    "contract_type": "auth_header",
                    "expected_value": "Authorization",
                    "locations": [],
                }
            ]
        ),
        contains="locations",
    )


def test_unsupported_shared_contract_type_severity_and_normalization_are_rejected():
    base = _complete_workspace()["shared_contracts"][0]
    for field, value in (
        ("contract_type", "jwt_cookie"),
        ("severity", "critical"),
        ("normalization", "slug"),
    ):
        contract = dict(base)
        contract[field] = value
        _expect_error(
            workspace_config.validate_workspace_config,
            _complete_workspace(shared_contracts=[contract]),
            contains=field,
        )


def test_location_path_normalization_and_unknown_repository_validation():
    location = workspace_config.SharedContractLocation(
        repository_id="frontend",
        path="src\\api\\.\\constants.ts",
        symbol="AUTH_HEADER",
    )

    assert location.to_dict()["path"] == "src/api/constants.ts"
    _expect_error(
        workspace_config.validate_workspace_config,
        _complete_workspace(
            shared_contracts=[
                {
                    "name": "authorization-header",
                    "contract_type": "auth_header",
                    "expected_value": "Authorization",
                    "locations": [
                        {
                            "repository_id": "mobile",
                            "path": "src/api/constants.ts",
                        }
                    ],
                }
            ]
        ),
        contains="unknown repository id",
    )
    _expect_error(
        workspace_config.SharedContractLocation,
        repository_id="frontend",
        path="../outside.ts",
        contains="location.path",
    )


def test_workspace_config_imports_are_scanner_compatible_and_layer_safe():
    config_source = (PROJECT_ROOT / "strata" / "utils" / "config.py").read_text(
        encoding="utf-8"
    )
    workspace_source = (
        PROJECT_ROOT / "strata" / "utils" / "workspace_config.py"
    ).read_text(encoding="utf-8")

    assert "import strata.utils.workspace_config as workspace_config" in config_source
    assert "from strata.utils import" not in config_source
    assert "strata.commands" not in workspace_source
    assert "strata.core" not in workspace_source


def test_workspace_q1_docs_define_contract_only_scope():
    content = (PROJECT_ROOT / "docs" / "roadmap" / "workspace-intelligence.md").read_text(
        encoding="utf-8"
    )

    assert "Q1 defines" in content
    assert "shared_contracts" in content
    assert "configuration references only" in content
    assert "does not read cross-repository files" in content


TESTS = [
    test_minimal_valid_workspace_is_json_ready,
    test_unsupported_workspace_schema_version_is_rejected,
    test_complete_workspace_serialization_is_deterministic,
    test_config_round_trip_preserves_unrelated_values_and_profile_overrides,
    test_repository_path_normalization_is_deterministic,
    test_supported_repository_roles_are_bounded,
    test_unsupported_repository_role_is_rejected,
    test_valid_and_invalid_ports_are_validated,
    test_supported_relationship_types_are_bounded,
    test_unsupported_relationship_type_is_rejected,
    test_self_relationship_is_rejected,
    test_unknown_repository_relationship_references_are_rejected,
    test_duplicate_repository_ids_are_rejected,
    test_shared_contract_with_multiple_locations_is_supported,
    test_shared_contract_missing_locations_is_rejected,
    test_unsupported_shared_contract_type_severity_and_normalization_are_rejected,
    test_location_path_normalization_and_unknown_repository_validation,
    test_workspace_config_imports_are_scanner_compatible_and_layer_safe,
    test_workspace_q1_docs_define_contract_only_scope,
]
