"""Deterministic JSON and XLSX exports for the calibration dashboard."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from src.modules.calibration_dashboard.schemas import EvidenceFilter



def _compose_dashboard(project_id: str, *, evidence_filter: EvidenceFilter):
    from src.modules.calibration_dashboard.service import compose_dashboard

    return compose_dashboard(project_id, evidence_filter=evidence_filter)


def _epoch():
    from src.modules.calibration_dashboard.service import EPOCH

    return EPOCH

def dashboard_json_bytes(
    project_id: str,
    *,
    evidence_filter: EvidenceFilter = "all",
) -> bytes:
    payload = _compose_dashboard(project_id, evidence_filter=evidence_filter).model_dump(
        mode="json"
    )
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _fit_sheet(sheet) -> None:
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        width = min(
            60,
            max(12, max(len(str(cell.value or "")) for cell in column) + 2),
        )
        sheet.column_dimensions[get_column_letter(column[0].column)].width = width
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")


def _normalize_zip(data: bytes) -> bytes:
    source = io.BytesIO(data)
    target = io.BytesIO()
    with zipfile.ZipFile(source, "r") as incoming, zipfile.ZipFile(
        target, "w", zipfile.ZIP_DEFLATED
    ) as outgoing:
        for name in sorted(incoming.namelist()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            content = incoming.read(name)
            if name == "docProps/core.xml":
                content = _normalize_core_properties(content)
            outgoing.writestr(info, content)
    return target.getvalue()


def _normalize_core_properties(xml_data: bytes) -> bytes:
    xml = xml_data.decode("utf-8")
    xml = re.sub(
        r"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
        r"\g<1>1970-01-01T00:00:00Z\g<2>",
        xml,
    )
    xml = re.sub(
        r"(<dcterms:created[^>]*>)[^<]*(</dcterms:created>)",
        r"\g<1>1970-01-01T00:00:00Z\g<2>",
        xml,
    )
    return xml.encode("utf-8")


def dashboard_xlsx_bytes(
    project_id: str,
    *,
    evidence_filter: EvidenceFilter = "all",
) -> bytes:
    dashboard = _compose_dashboard(project_id, evidence_filter=evidence_filter)
    workbook = Workbook()
    workbook.properties.creator = "Arvectum Creative Test Agent"
    workbook.properties.title = "Calibration Quality Dashboard"
    workbook.properties.created = _epoch().replace(tzinfo=None)
    workbook.properties.modified = _epoch().replace(tzinfo=None)

    summary = workbook.active
    summary.title = "Summary"
    summary.append(["Field", "Value"])
    summary.append(["Project ID", dashboard.project_id])
    summary.append(["Evidence filter", dashboard.evidence_filter])
    summary.append(["Generated from latest evidence", dashboard.generated_at.isoformat()])
    summary.append(["Schema version", dashboard.schema_version])
    summary.append(["Definitions version", dashboard.definitions_version])
    summary.append(["Validated model accuracy claimed", "false"])
    summary.append(["Causal interpretation allowed", "false"])
    summary.append(["Automatic threshold tuning", "false"])
    _fit_sheet(summary)

    metrics = workbook.create_sheet("Metrics")
    metrics.append(
        [
            "key",
            "label",
            "domain",
            "unit",
            "value",
            "numerator",
            "denominator",
            "coverage",
            "evidence_status",
            "definition",
            "interpretation",
            "limitations",
        ]
    )
    for item in dashboard.metrics:
        metrics.append(
            [
                item.key,
                item.label,
                item.domain,
                item.unit,
                item.value,
                item.numerator,
                item.denominator,
                item.coverage,
                item.evidence_status,
                item.definition,
                item.interpretation,
                " | ".join(item.limitations),
            ]
        )
    _fit_sheet(metrics)

    cases = workbook.create_sheet("Cases")
    cases.append(
        [
            "case_id",
            "campaign_id",
            "evidence_class",
            "inclusion_status",
            "system_findings",
            "resolved_findings",
            "unresolved_findings",
            "human_added_findings",
            "outcome_observations",
            "workflow_measurements",
            "operator_touch_seconds",
            "manual_action_count",
        ]
    )
    for item in dashboard.cases:
        cases.append(
            [
                item.case_id,
                item.campaign_id,
                item.evidence_class,
                item.inclusion_status,
                item.system_finding_count,
                item.resolved_finding_count,
                item.unresolved_finding_count,
                item.human_added_finding_count,
                item.outcome_observation_count,
                item.workflow_measurement_count,
                item.operator_touch_seconds,
                item.manual_action_count,
            ]
        )
    _fit_sheet(cases)

    claims = workbook.create_sheet("Claim Boundary")
    claims.append(["claim", "allowed_or_performed"])
    for key, value in sorted(dashboard.claim_boundary.items()):
        claims.append([key, str(value).lower()])
    for item in dashboard.limitations:
        claims.append(["limitation", item])
    _fit_sheet(claims)

    raw = io.BytesIO()
    workbook.save(raw)
    return _normalize_zip(raw.getvalue())


def export_manifest(
    project_id: str,
    *,
    evidence_filter: EvidenceFilter = "all",
) -> dict[str, Any]:
    json_data = dashboard_json_bytes(project_id, evidence_filter=evidence_filter)
    xlsx_data = dashboard_xlsx_bytes(project_id, evidence_filter=evidence_filter)
    dashboard = _compose_dashboard(project_id, evidence_filter=evidence_filter)
    return {
        "schema_version": "calibration-quality-dashboard-export/1.0",
        "project_id": project_id,
        "evidence_filter": evidence_filter,
        "generated_at": dashboard.generated_at.isoformat(),
        "claim_boundary": dashboard.claim_boundary,
        "files": [
            {
                "name": "calibration_dashboard.json",
                "size_bytes": len(json_data),
                "sha256": hashlib.sha256(json_data).hexdigest(),
            },
            {
                "name": "calibration_dashboard.xlsx",
                "size_bytes": len(xlsx_data),
                "sha256": hashlib.sha256(xlsx_data).hexdigest(),
            },
        ],
    }
