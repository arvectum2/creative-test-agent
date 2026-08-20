# Arvectum OS P8.06 onboarding boundary

Status: Product-local provisional integration evidence  
Owner: ООО «Арвектум»  
Consumer repository: `arvectum/creative-test-agent`  
Consumer kind: external extension  
Extension identity: `extension:creative-test-agent-audit-reconstruction@arvectum`  
Extension version: `0.1.0`

## Purpose

This artifact declares a bounded, optional and read-only integration boundary used by Arvectum OS `P8.06` to prove onboarding of a separately maintained external consumer. The extension may request governed reconstruction of evidence for Creative Test Agent operations. Creative Test Agent remains independently operable when this extension is disabled or absent.

The machine-checkable product-owned declaration is `integrations/arvectum_os_p8_06_onboarding.json`. Its format is owned by this product and is **not** a stable Arvectum OS public manifest format.

## Exact governed dependency

The extension declares one platform dependency only:

- dependency: `platform-capability:CAP-004@platform` — Audit / Reconstruction Support;
- exact capability contract version: `1.0.0`;
- allowed operation: `p3.08.reconstruct-execution`;
- requested right: `read`;
- required gates: `Authorization` and `DataGovernance`;
- failure behavior: fail closed if the exact version, operation, current provider evidence, Organization scope or access context cannot be established.

Compatibility is not inferred from nearby versions. Registration/onboarding does not grant authentication, authorization, Organizational Authority, lifecycle promotion or permission to mutate canonical state.

## Boundary and ownership

The only allowed integration mechanism is an explicit governed platform contract. The extension does not depend on Arvectum OS internal tables, private modules, private event streams, undocumented endpoints or implicit shared mutable state.

Creative Test Agent keeps ownership of its product semantics, including creative input/asset schemas, audience simulation and scoring, brand-safety/rubric configuration, creative-test workflows and approvals, reports/recommendations/UX, and model/prompt choices. None of those schemas or workflows become platform semantics through this onboarding proof.

The extension itself performs no canonical mutation. CAP-004 reconstruction is treated as a derived read-only evidence view with provenance, redaction and incompleteness preserved by the platform capability.

## Lifecycle path

**Install / declare.** Add the product-owned declaration. This alone does not activate platform reliance.

**Onboard / enable.** Arvectum OS must resolve the exact Provisional Product Contract, exact consumer identity/version, exact CAP-004 contract version and current governed provider evidence before reliance is enabled.

**Disable.** Stop all extension reliance. Creative Test Agent product state and Arvectum OS canonical state are unchanged by disabling this read-only extension.

**Remove.** Remove product-side integration reliance only after disable. Governance/audit evidence may be retained where required by applicable policy, but no hidden shared runtime state is required for removal.

**Upgrade.** Publish a new immutable product declaration version and a new Product Contract version, then rerun exact governed dependency resolution. No semver inference, auto-fallback or silent migration is permitted.

## Non-claims

This evidence does not make CAP-004 `Active`; it remains governed by its current capability lifecycle. It does not promote the Product Contract to `Stable`, create a public SDK/API guarantee, create a marketplace/registry commitment, or make Arvectum OS a mandatory runtime dependency of Creative Test Agent.
