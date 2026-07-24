from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

REPORT_ID = "provisional-client-one-page-report"
REPORT_VERSION = "1.0.0"
ALLOWED_LOCALES = {"ru", "en"}
ARTIFACT_MEDIA_TYPES = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "html": "text/html; charset=utf-8",
    "evidence": "application/json",
}
SEVERITY_RANK = {"blocking": 0, "warning": 1, "info": 2}

_TEXT = {
    "ru": {
        "title": "Предварительный pre-test креативов",
        "subtitle": "Одностраничное резюме доказательств и ограничений",
        "provisional": "Предварительный отчёт. Не является прогнозом эффективности или юридическим заключением.",
        "main_conclusion": "Основной вывод",
        "evidence_base": "Доказательная база",
        "capabilities": "Готовность возможностей",
        "limitations": "Ключевые ограничения",
        "next_actions": "Следующие действия",
        "allowed": "Что допустимо сказать",
        "source_files": "исходных файлов",
        "source_rows": "строк данных",
        "creative_links": "связанных креативов",
        "issues": "замечаний качества",
        "survey": "опросные ответы",
        "not_evaluated": "не оценено",
        "status_ready": "готово",
        "status_degraded": "ограниченно",
        "status_unavailable": "недоступно",
        "status_not_applicable": "не применимо",
        "evidence_strong": "сильная база",
        "evidence_moderate": "умеренная база",
        "evidence_weak": "слабая база",
        "evidence_none": "нет базы",
        "verdict_blocked_title": "Клиентский вывод заблокирован",
        "verdict_blocked_summary": "Есть блокирующие проблемы входных данных. Допустим только разбор пробелов и план исправления.",
        "verdict_limited_title": "Доступен только описательный разбор",
        "verdict_limited_summary": "Доказательств недостаточно для прогнозных или сравнительных выводов; ограничения должны быть показаны клиенту.",
        "verdict_review_title": "Доступен контролируемый экспертный разбор",
        "verdict_review_summary": "Материалы можно обсуждать, но часть возможностей работает в ограниченном режиме и требует экспертной проверки.",
        "verdict_ready_title": "Готово к контролируемому клиентскому обсуждению",
        "verdict_ready_summary": "Технические проверки пройдены; выводы остаются ограничены доступными источниками и не являются обещанием рыночного эффекта.",
        "no_limits": "Дополнительные ограничения не выявлены; действуют общие границы отчёта.",
        "no_actions": "Зафиксировать экспертное решение и сохранить обратную связь по каждому выводу.",
        "no_allowed": "Пока допустимо сообщать только состав данных, статус проверки и выявленные ограничения.",
        "survey_none": "опрос не выбран",
        "survey_synthetic": "синтетический proxy",
        "survey_human": "ответы людей",
        "survey_imported": "импортированные ответы",
        "survey_mixed": "смешанные источники",
        "provenance": "Источник",
        "dq": "качество данных",
        "readiness": "готовность",
        "source_sha": "SHA-256 источника",
        "generated": "сформировано",
        "page_footer": "Без общего балла, выдуманного CTR, causal lift и скрытой подмены недоступных возможностей.",
    },
    "en": {
        "title": "Provisional creative pre-test",
        "subtitle": "One-page evidence and limitations summary",
        "provisional": "Provisional report. Not a performance forecast or legal opinion.",
        "main_conclusion": "Main conclusion",
        "evidence_base": "Evidence base",
        "capabilities": "Capability readiness",
        "limitations": "Key limitations",
        "next_actions": "Next actions",
        "allowed": "Supported statements",
        "source_files": "source files",
        "source_rows": "data rows",
        "creative_links": "linked creatives",
        "issues": "quality issues",
        "survey": "survey responses",
        "not_evaluated": "not evaluated",
        "status_ready": "ready",
        "status_degraded": "limited",
        "status_unavailable": "unavailable",
        "status_not_applicable": "not applicable",
        "evidence_strong": "strong evidence",
        "evidence_moderate": "moderate evidence",
        "evidence_weak": "weak evidence",
        "evidence_none": "no evidence",
        "verdict_blocked_title": "Client conclusion blocked",
        "verdict_blocked_summary": "Blocking input-data issues remain. Only gap analysis and remediation planning are supported.",
        "verdict_limited_title": "Descriptive review only",
        "verdict_limited_summary": "Evidence is insufficient for predictive or comparative conclusions; limitations must be shown to the client.",
        "verdict_review_title": "Controlled expert review available",
        "verdict_review_summary": "The materials may be discussed, but some capabilities remain limited and require expert review.",
        "verdict_ready_title": "Ready for controlled client discussion",
        "verdict_ready_summary": "Technical checks passed; statements remain bounded by available evidence and are not a promise of market effect.",
        "no_limits": "No additional limitations were identified; the general report boundaries still apply.",
        "no_actions": "Record the expert decision and retain finding-level feedback.",
        "no_allowed": "Only data coverage, review status and identified limitations are currently supported.",
        "survey_none": "no study selected",
        "survey_synthetic": "synthetic proxy",
        "survey_human": "human responses",
        "survey_imported": "imported responses",
        "survey_mixed": "mixed sources",
        "provenance": "Source",
        "dq": "data quality",
        "readiness": "readiness",
        "source_sha": "source SHA-256",
        "generated": "generated",
        "page_footer": "No composite score, fabricated CTR, causal lift, or silent substitution of unavailable capabilities.",
    },
}

_COLORS = {
    "navy": "17233C",
    "graphite": "313643",
    "white": "FFFFFF",
    "paper": "F5F6F8",
    "line": "D9DEE8",
    "purple": "6C4DD8",
    "orange": "E4863A",
    "green": "2F855A",
    "amber": "B7791F",
    "red": "C53030",
    "muted": "657084",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _clean_text(value: Any, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"


def _unique_text(values: list[Any], *, limit: int, item_limit: int = 220) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value, item_limit)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def determine_verdict(data_quality_status: str, readiness_status: str) -> str:
    if data_quality_status == "blocked":
        return "blocked"
    if readiness_status == "unavailable":
        return "evidence_limited"
    if data_quality_status == "review_required" or readiness_status == "degraded":
        return "review_required"
    return "controlled_review_ready"


def _survey_summary(survey: dict[str, Any] | None, locale: str) -> dict[str, Any]:
    t = _TEXT[locale]
    if not survey:
        return {
            "selected": False,
            "total_responses": 0,
            "source_counts": {},
            "evidence_type": "none",
            "label": t["survey_none"],
            "real_human_response_count": 0,
            "synthetic_response_count": 0,
            "imported_response_count": 0,
        }
    source_counts = dict(survey.get("source_counts") or {})
    human = int(source_counts.get("human", 0) or 0)
    synthetic = int(source_counts.get("synthetic", 0) or 0)
    imported = int(source_counts.get("imported", 0) or 0)
    active = sum(1 for value in (human, synthetic, imported) if value > 0)
    if active > 1:
        evidence_type, label = "mixed", t["survey_mixed"]
    elif human:
        evidence_type, label = "human_quantitative", t["survey_human"]
    elif imported:
        evidence_type, label = "imported_quantitative", t["survey_imported"]
    elif synthetic:
        evidence_type, label = "synthetic_proxy", t["survey_synthetic"]
    else:
        evidence_type, label = "none", t["survey_none"]
    return {
        "selected": True,
        "study_id": (survey.get("study") or {}).get("id"),
        "study_status": (survey.get("study") or {}).get("status"),
        "total_responses": int(survey.get("total_responses", 0) or 0),
        "source_counts": source_counts,
        "metric_keys": list(survey.get("metric_keys") or []),
        "evidence_type": evidence_type,
        "label": label,
        "real_human_response_count": human,
        "synthetic_response_count": synthetic,
        "imported_response_count": imported,
        "interpretation_notes": list(survey.get("interpretation_notes") or []),
    }


def compose_report_evidence(
    context: dict[str, Any],
    *,
    locale: str = "ru",
    survey: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if locale not in ALLOWED_LOCALES:
        raise ValueError(f"Unsupported report locale: {locale}")
    t = _TEXT[locale]
    quality = context["data_quality"]
    readiness = context["prediction_readiness"]
    issues = sorted(
        list(context.get("issues") or []),
        key=lambda item: (
            SEVERITY_RANK.get(str(item.get("severity")), 9),
            -int(item.get("affected_count", 0) or 0),
            str(item.get("code", "")),
        ),
    )
    capabilities = sorted(
        list(context.get("capabilities") or []),
        key=lambda item: str(item.get("capability_key", "")),
    )
    survey_summary = _survey_summary(survey, locale)
    verdict = determine_verdict(str(quality["overall_status"]), str(readiness["overall_status"]))
    verdict_key = {
        "blocked": "blocked",
        "evidence_limited": "limited",
        "review_required": "review",
        "controlled_review_ready": "ready",
    }[verdict]

    allowed = _unique_text(
        [
            item.get("user_message")
            for item in capabilities
            if item.get("status") in {"ready", "degraded"}
        ],
        limit=3,
        item_limit=190,
    )
    if not allowed:
        allowed = [t["no_allowed"]]

    missing_inputs: list[str] = []
    prohibited: list[str] = []
    for item in capabilities:
        missing_inputs.extend(item.get("missing_inputs") or [])
        missing_inputs.extend(item.get("degraded_inputs") or [])
        prohibited.extend(item.get("prohibited_operations") or [])
    prohibited.extend(
        [
            "Do not present technical readiness as model accuracy.",
            "Do not present historical CTR as causal creative lift.",
            "Do not present synthetic responses as real people.",
            "Do not claim market effectiveness from this report.",
        ]
    )

    limitations = _unique_text(
        [item.get("message") for item in issues if item.get("severity") in {"blocking", "warning"}]
        + missing_inputs
        + list(survey_summary.get("interpretation_notes") or []),
        limit=4,
        item_limit=175,
    )
    if not limitations:
        limitations = [t["no_limits"]]

    next_actions = _unique_text(
        [item.get("remediation_hint") for item in issues if item.get("remediation_hint")]
        + missing_inputs
        + (["Resolve open client clarification questions."] if readiness.get("unresolved_client_question_count") else [])
        + (["Resolve open analyst clarification questions."] if readiness.get("unresolved_analyst_question_count") else []),
        limit=4,
        item_limit=175,
    )
    if not next_actions:
        next_actions = [t["no_actions"]]

    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "report_id": REPORT_ID,
        "report_version": REPORT_VERSION,
        "locale": locale,
        "generated_at": generated_at,
        "client": dict(context.get("client") or {}),
        "project": dict(context.get("project") or {}),
        "source": dict(context.get("source") or {}),
        "verdict": {
            "code": verdict,
            "title": t[f"verdict_{verdict_key}_title"],
            "summary": t[f"verdict_{verdict_key}_summary"],
        },
        "data_quality": quality,
        "prediction_readiness": readiness,
        "capabilities": capabilities,
        "survey": survey_summary,
        "top_issues": issues[:5],
        "supported_statements": allowed,
        "limitations": limitations,
        "next_actions": next_actions,
        "prohibited_statements": _unique_text(prohibited, limit=12, item_limit=220),
        "provenance": dict(context.get("provenance") or {}),
        "claim_boundary": {
            "provisional_report": True,
            "technical_readiness_is_not_model_accuracy": True,
            "market_effectiveness_not_evaluated": True,
            "prediction_generated": False,
            "causal_creative_lift_estimated": False,
            "composite_score_generated": False,
            "synthetic_responses_must_remain_labelled": True,
            "client_methodology_final": False,
        },
    }


def _rgb(name: str) -> RGBColor:
    return RGBColor.from_string(_COLORS[name])


def _add_rect(slide, x, y, w, h, *, fill: str, line: str | None = None, radius: bool = False):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(fill)
    shape.line.color.rgb = _rgb(line or fill)
    if radius:
        shape.adjustments[0] = 0.12
    return shape


def _add_text(
    slide,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    size: float = 12,
    color: str = "graphite",
    bold: bool = False,
    align=PP_ALIGN.LEFT,
    valign=MSO_ANCHOR.TOP,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Pt(0)
    frame.margin_right = Pt(0)
    frame.margin_top = Pt(0)
    frame.margin_bottom = Pt(0)
    frame.vertical_anchor = valign
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run()
    run.text = text
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = _rgb(color)
    return box


def _add_bullets(slide, values: list[str], x: float, y: float, w: float, h: float, *, size: float = 10.5):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Pt(0)
    frame.margin_right = Pt(0)
    frame.margin_top = Pt(0)
    frame.margin_bottom = Pt(0)
    for index, value in enumerate(values):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = "• " + _clean_text(value, 180)
        paragraph.font.name = "Arial"
        paragraph.font.size = Pt(size)
        paragraph.font.color.rgb = _rgb("graphite")
        paragraph.space_after = Pt(3)
    return box


def _status_color(status: str) -> str:
    return {
        "ready": "green",
        "degraded": "amber",
        "unavailable": "red",
        "not_applicable": "muted",
    }.get(status, "muted")


def _verdict_color(verdict: str) -> str:
    return {
        "blocked": "red",
        "evidence_limited": "amber",
        "review_required": "orange",
        "controlled_review_ready": "green",
    }[verdict]


def _status_label(status: str, locale: str) -> str:
    return _TEXT[locale].get(f"status_{status}", status.replace("_", " "))


def _evidence_label(status: str, locale: str) -> str:
    return _TEXT[locale].get(f"evidence_{status}", status.replace("_", " "))


def render_pptx(evidence: dict[str, Any], path: Path) -> None:
    locale = evidence["locale"]
    t = _TEXT[locale]
    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    presentation.core_properties.title = t["title"]
    presentation.core_properties.subject = t["provisional"]
    presentation.core_properties.author = "Arvectum"
    generated = datetime.fromisoformat(evidence["generated_at"].replace("Z", "+00:00"))
    presentation.core_properties.created = generated.replace(tzinfo=None)
    presentation.core_properties.modified = generated.replace(tzinfo=None)
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    background = slide.background.fill
    background.solid()
    background.fore_color.rgb = _rgb("paper")

    _add_rect(slide, 0, 0, 13.333, 0.9, fill="navy")
    _add_text(slide, t["title"], 0.45, 0.18, 7.7, 0.35, size=23, color="white", bold=True)
    client_name = _clean_text((evidence.get("client") or {}).get("name") or "Client", 70)
    project_name = _clean_text((evidence.get("project") or {}).get("name") or "Project", 70)
    _add_text(slide, f"{client_name} · {project_name}", 0.47, 0.57, 7.7, 0.18, size=9.5, color="white")
    verdict = evidence["verdict"]
    _add_rect(slide, 9.55, 0.19, 3.25, 0.48, fill=_verdict_color(verdict["code"]), radius=True)
    _add_text(slide, _clean_text(verdict["title"], 58), 9.68, 0.28, 2.98, 0.22, size=10.5, color="white", bold=True, align=PP_ALIGN.CENTER)

    _add_rect(slide, 0.45, 1.1, 4.05, 1.82, fill="white", line="line", radius=True)
    _add_text(slide, t["main_conclusion"], 0.7, 1.3, 3.55, 0.25, size=12, color="purple", bold=True)
    _add_text(slide, _clean_text(verdict["title"], 90), 0.7, 1.62, 3.55, 0.46, size=16, color="navy", bold=True)
    _add_text(slide, _clean_text(verdict["summary"], 310), 0.7, 2.12, 3.55, 0.58, size=10.5, color="graphite")

    _add_rect(slide, 0.45, 3.08, 4.05, 3.52, fill="white", line="line", radius=True)
    _add_text(slide, t["evidence_base"], 0.7, 3.28, 3.55, 0.24, size=12, color="purple", bold=True)
    quality = evidence["data_quality"]
    survey = evidence["survey"]
    facts = [
        f"{quality.get('source_file_count', 0)} {t['source_files']}",
        f"{quality.get('source_row_count', 0)} {t['source_rows']}",
        f"{quality.get('linked_creative_count', 0)}/{quality.get('creative_record_count', 0)} {t['creative_links']}",
        f"{quality.get('total_issue_count', 0)} {t['issues']}",
        f"{survey.get('total_responses', 0)} {t['survey']} · {survey.get('label', t['survey_none'])}",
    ]
    for index, fact in enumerate(facts):
        y = 3.67 + index * 0.34
        _add_rect(slide, 0.7, y, 0.10, 0.10, fill="orange", radius=True)
        _add_text(slide, fact, 0.9, y - 0.02, 3.25, 0.18, size=10.2, color="graphite")
    _add_text(slide, t["allowed"], 0.7, 5.45, 3.55, 0.22, size=11, color="purple", bold=True)
    _add_bullets(slide, evidence["supported_statements"][:2], 0.7, 5.76, 3.55, 0.65, size=9.2)

    _add_rect(slide, 4.72, 1.1, 8.16, 2.72, fill="white", line="line", radius=True)
    _add_text(slide, t["capabilities"], 4.97, 1.3, 7.65, 0.25, size=12, color="purple", bold=True)
    for label, x, w in (("Capability", 5.0, 3.65), ("Status", 8.72, 1.25), ("Mode / evidence", 10.04, 2.55)):
        _add_text(slide, label, x, 1.66, w, 0.18, size=8.6, color="muted", bold=True)
    capabilities = evidence.get("capabilities") or []
    for index, item in enumerate(capabilities[:5]):
        y = 1.95 + index * 0.34
        if index:
            _add_rect(slide, 4.98, y - 0.07, 7.63, 0.01, fill="line")
        _add_text(slide, _clean_text(item.get("title") or item.get("capability_key"), 58), 5.0, y, 3.55, 0.18, size=9.2, color="graphite")
        color = _status_color(str(item.get("status")))
        _add_rect(slide, 8.72, y - 0.02, 1.12, 0.23, fill=color, radius=True)
        _add_text(slide, _status_label(str(item.get("status")), locale), 8.76, y + 0.015, 1.04, 0.13, size=7.8, color="white", bold=True, align=PP_ALIGN.CENTER)
        mode = _clean_text(item.get("mode"), 32)
        evidence_label = _evidence_label(str(item.get("evidence_strength")), locale)
        _add_text(slide, f"{mode} · {evidence_label}", 10.04, y, 2.52, 0.18, size=8.6, color="graphite")
    if not capabilities:
        _add_text(slide, t["not_evaluated"], 5.0, 2.05, 7.5, 0.3, size=11, color="muted")

    _add_rect(slide, 4.72, 4.0, 3.97, 2.6, fill="white", line="line", radius=True)
    _add_text(slide, t["limitations"], 4.97, 4.2, 3.48, 0.24, size=12, color="purple", bold=True)
    _add_bullets(slide, evidence["limitations"][:3], 4.97, 4.55, 3.48, 1.75, size=9.4)
    _add_rect(slide, 8.91, 4.0, 3.97, 2.6, fill="white", line="line", radius=True)
    _add_text(slide, t["next_actions"], 9.16, 4.2, 3.48, 0.24, size=12, color="purple", bold=True)
    _add_bullets(slide, evidence["next_actions"][:3], 9.16, 4.55, 3.48, 1.75, size=9.4)

    provenance = evidence.get("provenance") or {}
    source_sha = str((evidence.get("source") or {}).get("sha256") or "")[:12]
    footer = (
        f"{t['provenance']}: {t['dq']} {str(provenance.get('data_quality_run_id', ''))[:8]} · "
        f"{t['readiness']} {str(provenance.get('prediction_readiness_run_id', ''))[:8]} · "
        f"{t['source_sha']} {source_sha} · {t['generated']} {evidence['generated_at'][:10]}"
    )
    _add_text(slide, footer, 0.47, 6.84, 8.8, 0.18, size=7.8, color="muted")
    _add_text(slide, t["page_footer"], 7.75, 6.82, 5.1, 0.26, size=7.6, color="muted", align=PP_ALIGN.RIGHT)
    _add_text(slide, t["provisional"], 0.47, 7.14, 12.35, 0.17, size=7.3, color="muted", align=PP_ALIGN.CENTER)

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as raw:
        temporary = Path(raw) / "raw.pptx"
        presentation.save(temporary)
        _normalize_pptx_zip(temporary, path)


def _normalize_pptx_zip(source: Path, target: Path) -> None:
    with ZipFile(source, "r") as archive, ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=9) as output:
        for name in sorted(archive.namelist()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            output.writestr(info, archive.read(name))


def _html_list(values: list[str]) -> str:
    return "".join(f"<li>{html.escape(_clean_text(item, 220))}</li>" for item in values)


def render_html(evidence: dict[str, Any], path: Path) -> None:
    locale = evidence["locale"]
    t = _TEXT[locale]
    quality = evidence["data_quality"]
    survey = evidence["survey"]
    capability_rows = []
    for item in evidence.get("capabilities") or []:
        status = str(item.get("status"))
        capability_rows.append(
            "<tr>"
            f"<td>{html.escape(_clean_text(item.get('title') or item.get('capability_key'), 90))}</td>"
            f"<td><span class='badge {html.escape(status)}'>{html.escape(_status_label(status, locale))}</span></td>"
            f"<td>{html.escape(_clean_text(item.get('mode'), 50))}</td>"
            f"<td>{html.escape(_evidence_label(str(item.get('evidence_strength')), locale))}</td>"
            "</tr>"
        )
    if not capability_rows:
        capability_rows.append(f"<tr><td colspan='4'>{html.escape(t['not_evaluated'])}</td></tr>")
    client_name = html.escape(_clean_text((evidence.get("client") or {}).get("name") or "Client", 100))
    project_name = html.escape(_clean_text((evidence.get("project") or {}).get("name") or "Project", 100))
    verdict = evidence["verdict"]
    provenance = evidence.get("provenance") or {}
    document = f"""<!doctype html>
<html lang="{locale}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(t['title'])}</title><style>
@page {{ size: A4 landscape; margin: 0; }}
* {{ box-sizing: border-box; }} html, body {{ margin:0; padding:0; background:#e9ebef; font-family:Arial,sans-serif; color:#313643; }}
.page {{ width:297mm; height:210mm; margin:0 auto; background:#F5F6F8; overflow:hidden; position:relative; page-break-after:avoid; }}
.header {{ height:27mm; background:#17233C; color:white; padding:6mm 10mm; display:flex; justify-content:space-between; align-items:flex-start; }}
h1 {{ margin:0; font-size:22pt; line-height:1.05; }} .sub {{ margin-top:2mm; font-size:9pt; opacity:.9; }}
.verdict {{ max-width:78mm; padding:3mm 5mm; border-radius:6mm; font-weight:700; text-align:center; background:#{_COLORS[_verdict_color(verdict['code'])]}; }}
.grid {{ display:grid; grid-template-columns:92mm 1fr; gap:5mm; padding:5mm 10mm 0; }} .card {{ background:white; border:1px solid #D9DEE8; border-radius:4mm; padding:5mm; }}
.left {{ display:grid; grid-template-rows:51mm 91mm; gap:5mm; }} .right {{ display:grid; grid-template-rows:76mm 66mm; gap:5mm; }} .bottom {{ display:grid; grid-template-columns:1fr 1fr; gap:5mm; }}
h2 {{ margin:0 0 3mm; color:#6C4DD8; font-size:11pt; }} h3 {{ margin:0 0 2mm; color:#17233C; font-size:15pt; }} p {{ margin:0; font-size:9pt; line-height:1.32; }}
ul {{ margin:0; padding-left:5mm; font-size:8.5pt; line-height:1.28; }} li {{ margin-bottom:1.7mm; }} .facts {{ display:grid; grid-template-columns:1fr 1fr; gap:2mm; margin-bottom:4mm; }}
.fact {{ background:#F5F6F8; border-radius:2mm; padding:2.5mm; font-size:8.5pt; }} table {{ width:100%; border-collapse:collapse; font-size:8.3pt; }} th {{ text-align:left; color:#657084; border-bottom:1px solid #D9DEE8; padding:1.8mm; }}
td {{ border-bottom:1px solid #ECEEF2; padding:1.8mm; }} .badge {{ display:inline-block; color:white; border-radius:3mm; padding:1mm 2.5mm; font-size:7.5pt; font-weight:700; }}
.ready {{ background:#2F855A; }} .degraded {{ background:#B7791F; }} .unavailable {{ background:#C53030; }} .not_applicable {{ background:#657084; }}
.footer {{ position:absolute; left:10mm; right:10mm; bottom:4mm; border-top:1px solid #D9DEE8; padding-top:2mm; display:flex; justify-content:space-between; gap:5mm; font-size:6.8pt; color:#657084; }}
@media print {{ html, body {{ background:white; }} .page {{ margin:0; }} }}
</style></head><body><main class="page" data-page-count="1">
<header class="header"><div><h1>{html.escape(t['title'])}</h1><div class="sub">{client_name} · {project_name}<br>{html.escape(t['subtitle'])}</div></div><div class="verdict">{html.escape(verdict['title'])}</div></header>
<section class="grid"><div class="left"><div class="card"><h2>{html.escape(t['main_conclusion'])}</h2><h3>{html.escape(verdict['title'])}</h3><p>{html.escape(verdict['summary'])}</p></div>
<div class="card"><h2>{html.escape(t['evidence_base'])}</h2><div class="facts"><div class="fact"><b>{quality.get('source_file_count', 0)}</b> {html.escape(t['source_files'])}</div><div class="fact"><b>{quality.get('source_row_count', 0)}</b> {html.escape(t['source_rows'])}</div>
<div class="fact"><b>{quality.get('linked_creative_count', 0)}/{quality.get('creative_record_count', 0)}</b> {html.escape(t['creative_links'])}</div><div class="fact"><b>{quality.get('total_issue_count', 0)}</b> {html.escape(t['issues'])}</div>
<div class="fact"><b>{survey.get('total_responses', 0)}</b> {html.escape(t['survey'])}</div><div class="fact">{html.escape(str(survey.get('label', t['survey_none'])))}</div></div><h2>{html.escape(t['allowed'])}</h2><ul>{_html_list(evidence['supported_statements'][:3])}</ul></div></div>
<div class="right"><div class="card"><h2>{html.escape(t['capabilities'])}</h2><table><thead><tr><th>Capability</th><th>Status</th><th>Mode</th><th>Evidence</th></tr></thead><tbody>{''.join(capability_rows)}</tbody></table></div>
<div class="bottom"><div class="card"><h2>{html.escape(t['limitations'])}</h2><ul>{_html_list(evidence['limitations'][:4])}</ul></div><div class="card"><h2>{html.escape(t['next_actions'])}</h2><ul>{_html_list(evidence['next_actions'][:4])}</ul></div></div></div></section>
<footer class="footer"><span>{html.escape(t['provenance'])}: DQ {html.escape(str(provenance.get('data_quality_run_id', ''))[:8])} · readiness {html.escape(str(provenance.get('prediction_readiness_run_id', ''))[:8])} · SHA {html.escape(str((evidence.get('source') or {}).get('sha256') or '')[:12])}</span><span>{html.escape(t['page_footer'])}</span><span>{html.escape(t['provisional'])}</span></footer>
</main></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")


def build_report_bundle(evidence: dict[str, Any], output_dir: Path, *, basename: str = "client_one_page_report", clean: bool = True) -> dict[str, Any]:
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pptx_path = output_dir / f"{basename}.pptx"
    html_path = output_dir / f"{basename}.html"
    evidence_path = output_dir / f"{basename}_evidence.json"
    render_pptx(evidence, pptx_path)
    render_html(evidence, html_path)
    evidence_path.write_bytes(_json_bytes(evidence))
    artifacts = []
    for artifact_type, path in (("pptx", pptx_path), ("html", html_path), ("evidence", evidence_path)):
        artifacts.append({"artifact_type": artifact_type, "filename": path.name, "media_type": ARTIFACT_MEDIA_TYPES[artifact_type], "sha256": _sha256_file(path), "size_bytes": path.stat().st_size})
    manifest = {
        "report_id": REPORT_ID,
        "report_version": REPORT_VERSION,
        "locale": evidence["locale"],
        "verdict": evidence["verdict"]["code"],
        "generated_at": evidence["generated_at"],
        "slide_count": 1,
        "page_count": 1,
        "artifacts": artifacts,
        "claim_boundary": evidence["claim_boundary"],
        "model_selected": False,
        "prediction_generated": False,
        "market_effectiveness_not_evaluated": True,
    }
    manifest_path = output_dir / "report_manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest))
    manifest["manifest"] = {"filename": manifest_path.name, "sha256": _sha256_file(manifest_path), "size_bytes": manifest_path.stat().st_size, "media_type": "application/json"}
    return manifest


def validate_report_bundle(output_dir: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = output_dir / "report_manifest.json"
    if not manifest_path.is_file():
        return ["report_manifest.json is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"report manifest is unreadable: {exc}"]
    if manifest.get("report_id") != REPORT_ID or manifest.get("report_version") != REPORT_VERSION:
        errors.append("unexpected report identity or version")
    if manifest.get("slide_count") != 1 or manifest.get("page_count") != 1:
        errors.append("client report must remain one slide and one printable page")
    if manifest.get("model_selected") is not False or manifest.get("prediction_generated") is not False:
        errors.append("report must not select a model or generate a prediction")
    artifacts = manifest.get("artifacts") or []
    if {item.get("artifact_type") for item in artifacts} != {"pptx", "html", "evidence"}:
        errors.append("report artifacts must include pptx, html and evidence")
    for item in artifacts:
        path = output_dir / str(item.get("filename", ""))
        if not path.is_file():
            errors.append(f"missing report artifact: {path.name}")
            continue
        if path.stat().st_size != item.get("size_bytes"):
            errors.append(f"size mismatch for {path.name}")
        if _sha256_file(path) != item.get("sha256"):
            errors.append(f"SHA-256 mismatch for {path.name}")
    pptx = next((output_dir / item["filename"] for item in artifacts if item.get("artifact_type") == "pptx"), None)
    if pptx and pptx.is_file():
        try:
            if len(Presentation(pptx).slides) != 1:
                errors.append("PPTX must contain exactly one slide")
        except Exception as exc:
            errors.append(f"PPTX is unreadable: {exc}")
    html_path = next((output_dir / item["filename"] for item in artifacts if item.get("artifact_type") == "html"), None)
    if html_path and html_path.is_file():
        body = html_path.read_text(encoding="utf-8")
        if 'data-page-count="1"' not in body or "@page { size: A4 landscape; margin: 0; }" not in body:
            errors.append("HTML one-page print contract is missing")
    evidence_path = next((output_dir / item["filename"] for item in artifacts if item.get("artifact_type") == "evidence"), None)
    if evidence_path and evidence_path.is_file():
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"evidence JSON is unreadable: {exc}")
        else:
            boundary = evidence.get("claim_boundary") or {}
            expected = {
                "technical_readiness_is_not_model_accuracy": True,
                "market_effectiveness_not_evaluated": True,
                "prediction_generated": False,
                "causal_creative_lift_estimated": False,
                "composite_score_generated": False,
            }
            for key, value in expected.items():
                if boundary.get(key) is not value:
                    errors.append(f"claim boundary mismatch: {key}")
    return errors
