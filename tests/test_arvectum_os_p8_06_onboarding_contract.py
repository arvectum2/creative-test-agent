from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECLARATION = ROOT / "integrations" / "arvectum_os_p8_06_onboarding.json"


def _load() -> dict:
    return json.loads(DECLARATION.read_text(encoding="utf-8"))


def test_p8_06_declaration_is_product_owned_and_external() -> None:
    data = _load()
    consumer = data["consumer"]

    assert data["declaration_format_owner"] == "arvectum/creative-test-agent"
    assert data["declaration_format_status"] == "product-local-provisional-p8.06-evidence"
    assert consumer["kind"] == "extension"
    assert consumer["repository"] == "arvectum/creative-test-agent"
    assert consumer["identity"] == {
        "namespace": "extension",
        "value": "creative-test-agent-audit-reconstruction",
        "scope": "arvectum",
    }
    assert consumer["version"] == "0.1.0"
    assert consumer["organization_id"] == "arvectum"


def test_p8_06_dependency_is_exact_single_cap004_read_only_contract() -> None:
    data = _load()
    dependencies = data["dependencies"]

    assert len(dependencies) == 1
    dependency = dependencies[0]
    assert dependency["dependency_namespace"] == "platform-capability"
    assert dependency["dependency_id"] == "CAP-004"
    assert dependency["contract_version"] == "1.0.0"
    assert dependency["allowed_operations"] == ["p3.08.reconstruct-execution"]
    assert dependency["provisional"] is True
    assert "Fail closed" in dependency["failure_behavior"]

    least_privilege = data["least_privilege"]
    assert least_privilege["required_rights"] == ["read"]
    assert least_privilege["required_gates"] == ["Authorization", "DataGovernance"]
    assert least_privilege["organizational_authority_granted"] is False

    authority = data["authority_and_state"]
    assert authority["canonical_mutation_allowed"] is False
    assert authority["authorization_granted_by_registration"] is False
    assert authority["organizational_authority_granted_by_registration"] is False


def test_p8_06_boundary_forbids_private_coupling_and_hidden_shared_state() -> None:
    boundary = _load()["boundary"]

    assert boundary["mechanism"] == "declared-platform-contract"
    assert set(boundary["forbidden_reliance"]) == {
        "internal-table",
        "internal-import",
        "undocumented-endpoint",
        "private-event-stream",
        "implicit-shared-state",
    }
    assert boundary["shared_mutable_state"] is False
    assert boundary["platform_private_module_imports"] is False
    assert boundary["platform_internal_table_access"] is False
    assert boundary["platform_private_stream_access"] is False
    assert boundary["undocumented_endpoint_access"] is False


def test_p8_06_product_semantics_remain_product_owned() -> None:
    semantics = set(_load()["product_owned_semantics"])

    assert "creative input and asset schemas" in semantics
    assert "audience simulation and scoring semantics" in semantics
    assert "creative-test workflows and approvals" in semantics
    assert "reports, recommendations and product UX" in semantics
    assert "model and prompt choices" in semantics


def test_p8_06_lifecycle_is_reversible_and_upgrade_reresolves_exactly() -> None:
    lifecycle = _load()["lifecycle"]

    assert lifecycle["enabled_by_default"] is False
    assert "exact Provisional Product Contract" in lifecycle["onboard"]
    assert "Stop extension reliance" in lifecycle["disable"]
    assert "after disable" in lifecycle["remove"]
    assert "new immutable declaration version" in lifecycle["upgrade"]
    assert "re-run exact governed dependency resolution" in lifecycle["upgrade"]
    assert "never infer compatibility or auto-fallback" in lifecycle["upgrade"]


def test_p8_06_does_not_claim_public_api_or_lifecycle_promotion() -> None:
    data = _load()
    expectation = data["product_contract_expectation"]
    authority = data["authority_and_state"]

    assert expectation["canonical_owner"] == "arvectum/arvectum-os"
    assert expectation["lifecycle"] == "Provisional"
    assert authority["creates_platform_capability_lifecycle_transition"] is False
    assert authority["creates_stable_public_api_or_sdk"] is False
