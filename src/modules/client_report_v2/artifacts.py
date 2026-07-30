from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt as PptxPt

from src.modules.client_report_v2.evidence import REPORT_ID, REPORT_VERSION, clean, validate_evidence

ARTIFACT_MEDIA_TYPES = {
    "html": "text/html; charset=utf-8",
    "one_page_pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "full_pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "evidence": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
C = {"navy": "091426", "panel": "17263F", "teal": "3DD6C6", "purple": "8B5CF6", "paper": "F6F8FB", "white": "FFFFFF", "ink": "172033", "muted": "667085", "line": "D8DEE9"}
T = {
    "ru": {"title": "Evidence-bound отчёт по креативам", "subtitle": "Факты, диагностика агента, CG/TG outcomes, экспертная оценка и ограничения", "facts": "Наблюдаемые факты", "diagnostics": "Диагностика агента", "outcomes": "Фактические CG/TG outcomes", "expert": "Экспертная оценка", "limits": "Ограничения и confidence", "release": "Статус выпуска", "missing": "нет данных", "warning": "Предварительный диагностический отчёт. Не является прогнозом эффективности или доказательством причинного uplift."},
    "en": {"title": "Evidence-bound creative report", "subtitle": "Facts, agent diagnostics, CG/TG outcomes, expert assessment, limitations", "facts": "Observed facts", "diagnostics": "Agent diagnostics", "outcomes": "Factual CG/TG outcomes", "expert": "Expert assessment", "limits": "Limitations and confidence", "release": "Release status", "missing": "missing", "warning": "Provisional diagnostic report. Not a performance forecast or evidence of causal uplift."},
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def normalize_office_zip(source: Path, target: Path) -> None:
    with ZipFile(source, "r") as archive, ZipFile(target, "w", ZIP_DEFLATED, compresslevel=9) as output:
        for name in sorted(archive.namelist()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); info.compress_type = ZIP_DEFLATED; info.external_attr = 0o600 << 16
            payload = archive.read(name)
            if name == "docProps/core.xml":
                text = payload.decode("utf-8")
                for tag in ("created", "modified"):
                    text = re.sub(
                        rf"(<dcterms:{tag}[^>]*>).*?(</dcterms:{tag}>)",
                        rf"\g<1>2000-01-01T00:00:00Z\g<2>",
                        text,
                    )
                payload = text.encode("utf-8")
            output.writestr(info, payload)


def add_text(slide, text, x, y, w, h, *, size=12, color="white", bold=False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); frame = box.text_frame; frame.clear(); frame.word_wrap = True
    p = frame.paragraphs[0]; p.alignment = align; run = p.add_run(); run.text = clean(text, 1800); run.font.name = "Arial"; run.font.size = PptxPt(size); run.font.bold = bold; run.font.color.rgb = RGBColor.from_string(C.get(color, color)); return box


def rect(slide, x, y, w, h, fill="panel"):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)); shape.fill.solid(); shape.fill.fore_color.rgb = RGBColor.from_string(C[fill]); shape.line.color.rgb = RGBColor.from_string(C[fill]); return shape


def bullets(slide, values, x, y, w, h, *, size=9, max_items=7):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); frame = box.text_frame; frame.clear(); frame.word_wrap = True
    for index, value in enumerate(values[:max_items]):
        p = frame.paragraphs[0] if index == 0 else frame.add_paragraph(); p.text = "• " + clean(value, 320); p.font.name = "Arial"; p.font.size = PptxPt(size); p.font.color.rgb = RGBColor.from_string(C["ink"]); p.space_after = PptxPt(4)
    return box


def header(slide, title, subtitle=""):
    bg = slide.background.fill; bg.solid(); bg.fore_color.rgb = RGBColor.from_string(C["navy"]); add_text(slide, title, .55, .3, 12, .55, size=24, bold=True)
    if subtitle: add_text(slide, subtitle, .58, .92, 11.7, .35, size=9.5, color="teal")


def render_one_page_pptx(evidence: dict[str, Any], path: Path) -> None:
    t = T[evidence["locale"]]; s = evidence["summary"]; findings = evidence["agent_diagnostics"]["findings"]; outcomes = evidence["factual_outcomes"]["outcomes"]; limits = evidence["limitations_and_confidence"]["limitations"]
    prs = Presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5); slide = prs.slides.add_slide(prs.slide_layouts[6]); header(slide, t["title"], clean((evidence.get("project") or {}).get("name") or "Project", 100))
    labels = [(s["campaign_count"], "campaigns"), (s["asset_count"], "assets"), (s["finding_count"], "findings"), (s["reviewed_finding_count"], "expert-reviewed"), (s["outcome_count"], "CG/TG rows")]
    for i, (value, label) in enumerate(labels):
        x = .55 + i * 2.48; rect(slide, x, 1.3, 2.22, .72); add_text(slide, value, x+.15, 1.44, .5, .3, size=18, color="teal", bold=True); add_text(slide, label, x+.7, 1.47, 1.35, .25, size=8.5)
    for x, width, title, lines in [(.55, 4.0, t["diagnostics"], [f"{f['criterion']}: {f['text']} [{', '.join(f['evidence_references'])}]" for f in findings]), (4.72, 4.0, t["outcomes"], [f"{o.get('metric_label') or o.get('metric')}: CG={o.get('cg_rate')}; TG={o.get('tg_rate')}; descriptive Δ={o.get('uplift_pp_descriptive')} pp — campaign set" for o in outcomes])]:
        rect(slide, x, 2.25, width, 4.15, "paper"); add_text(slide, title, x+.28, 2.52, width-.55, .3, size=13, color="purple", bold=True); bullets(slide, lines or [t["missing"]], x+.28, 2.95, width-.55, 3.0, size=8.3)
    rect(slide, 8.9, 2.25, 3.9, 1.35); add_text(slide, t["release"], 9.2, 2.53, 3.2, .25, size=10, color="teal", bold=True); add_text(slide, s["release_status"], 9.2, 2.9, 3.2, .42, size=16, bold=True)
    rect(slide, 8.9, 3.82, 3.9, 2.58, "paper"); add_text(slide, t["limits"], 9.2, 4.1, 3.2, .3, size=13, color="purple", bold=True); bullets(slide, [item.get("message") for item in limits], 9.2, 4.5, 3.2, 1.55, size=8.0, max_items=5)
    add_text(slide, t["warning"], .7, 6.85, 11.9, .25, size=7.7, color="muted", align=PP_ALIGN.CENTER)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.pptx"; prs.save(raw); normalize_office_zip(raw, path)


def render_full_pptx(evidence: dict[str, Any], path: Path) -> None:
    t = T[evidence["locale"]]; prs = Presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6]); header(slide, t["title"], t["subtitle"]); rect(slide, .7, 1.6, 11.95, 3.5); add_text(slide, (evidence.get("project") or {}).get("name") or "Project", 1, 2.05, 11.2, .55, size=26, bold=True, align=PP_ALIGN.CENTER); add_text(slide, evidence["summary"]["release_status"], 1, 2.85, 11.2, .5, size=18, color="teal", bold=True, align=PP_ALIGN.CENTER); add_text(slide, t["warning"], 1.3, 3.7, 10.6, .5, size=10, color="muted", align=PP_ALIGN.CENTER)
    slide = prs.slides.add_slide(prs.slide_layouts[6]); header(slide, t["facts"], "Campaign-set outcomes and individual-asset diagnostics remain separate")
    cards = [("campaign_count", "campaigns"), ("asset_count", "assets"), ("finding_count", "findings"), ("reviewed_finding_count", "expert-reviewed"), ("outcome_count", "CG/TG rows"), ("limitation_count", "limitations")]
    for i, (key, label) in enumerate(cards):
        r, c = divmod(i, 3); x = .7 + c*4.12; y = 1.55 + r*2.2; rect(slide, x, y, 3.75, 1.65, "paper"); add_text(slide, evidence["summary"][key], x+.25, y+.35, .8, .45, size=23, color="purple", bold=True); add_text(slide, label, x+1.15, y+.42, 2.1, .35, size=11, color="ink", bold=True)
    findings_by_campaign = {}; outcomes_by_campaign = {}; expert = {item["finding_id"]: item for item in evidence["expert_assessment"]["assessments"]}
    for item in evidence["agent_diagnostics"]["findings"]: findings_by_campaign.setdefault(str(item.get("campaign_id")), []).append(item)
    for item in evidence["factual_outcomes"]["outcomes"]: outcomes_by_campaign.setdefault(str(item.get("campaign_id")), []).append(item)
    for campaign in evidence["observed_facts"]["campaigns"]:
        slide = prs.slides.add_slide(prs.slide_layouts[6]); title = " · ".join(filter(None, [str(campaign.get("brand") or ""), str(campaign.get("product") or ""), str(campaign.get("case_id") or "")])) or campaign["campaign_id"]; header(slide, title, "Scope: campaign set; asset diagnostics are shown separately")
        panels = [(.55, t["facts"], [f"Platform: {campaign.get('platform')}", f"Period: {campaign.get('period_start')} — {campaign.get('period_end')}", f"Assets: {len(campaign.get('assets') or [])}", "Individual asset outcome attribution: prohibited"] + [f"{a.get('title') or a.get('filename')}: {a.get('linkage_status')} ({a.get('linkage_confidence')})" for a in campaign.get("assets") or []]), (4.58, t["diagnostics"], [f"{f['criterion']}: {f['text']} | expert={expert.get(f['finding_id'], {}).get('verdict', 'not_reviewed')} | ref={f['evidence_references'][-1]}" for f in findings_by_campaign.get(campaign["campaign_id"], [])]), (8.76, t["outcomes"], [f"{o.get('metric_label')}: CG={o.get('cg_rate')}; TG={o.get('tg_rate')}; descriptive Δ={o.get('uplift_pp_descriptive')} pp | ref={o['evidence_references'][-1]}" for o in outcomes_by_campaign.get(campaign["campaign_id"], [])])]
        for x, title2, lines in panels: rect(slide, x, 1.42, 3.82, 5.35, "paper"); add_text(slide, title2, x+.28, 1.72, 3.25, .3, size=13, color="purple", bold=True); bullets(slide, lines or [t["missing"]], x+.28, 2.12, 3.25, 4.15, size=8.3, max_items=9)
    slide = prs.slides.add_slide(prs.slide_layouts[6]); header(slide, t["limits"], t["warning"]); rect(slide, .75, 1.5, 7.2, 5.25, "paper"); bullets(slide, [item.get("message") for item in evidence["limitations_and_confidence"]["limitations"]], 1.05, 1.9, 6.5, 4.2, size=9.5, max_items=12); rect(slide, 8.2, 1.5, 4.35, 5.25); add_text(slide, t["release"], 8.55, 1.95, 3.65, .3, size=12, color="teal", bold=True); add_text(slide, evidence["summary"]["release_status"], 8.55, 2.45, 3.65, .65, size=18, bold=True); add_text(slide, json.dumps(evidence["limitations_and_confidence"]["confidence_summary"], ensure_ascii=False, indent=2), 8.55, 3.45, 3.65, 2.1, size=8.5, color="muted")
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.pptx"; prs.save(raw); normalize_office_zip(raw, path)


def render_html(evidence: dict[str, Any], path: Path) -> None:
    t = T[evidence["locale"]]; esc = lambda v: html.escape(clean(v, 4000)); experts = {item["finding_id"]: item for item in evidence["expert_assessment"]["assessments"]}; s = evidence["summary"]
    findings = "".join(f"<tr><td>{esc(f['finding_id'])}</td><td>{esc(f['criterion'])}</td><td>{esc(f['text'])}</td><td>individual asset</td><td>{esc(f.get('confidence'))}</td><td>{esc(experts.get(f['finding_id'], {}).get('verdict'))}</td><td><code>{esc(', '.join(f['evidence_references']))}</code></td></tr>" for f in evidence["agent_diagnostics"]["findings"])
    outcomes = "".join(f"<tr><td>{esc(o['campaign_id'])}</td><td>{esc(o.get('metric_label') or o.get('metric'))}</td><td>{esc(o.get('cg_rate'))}</td><td>{esc(o.get('tg_rate'))}</td><td>{esc(o.get('uplift_pp_descriptive'))}</td><td>campaign set</td><td><code>{esc(', '.join(o['evidence_references']))}</code></td></tr>" for o in evidence["factual_outcomes"]["outcomes"])
    limits = "".join(f"<li><b>{esc(x.get('code'))}</b>: {esc(x.get('message'))}</li>" for x in evidence["limitations_and_confidence"]["limitations"])
    body = f"""<!doctype html><html lang='{evidence['locale']}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(t['title'])}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#eef1f6;color:#172033;font-family:Arial}}header,footer{{background:#091426;color:white;padding:28px 6vw;border-top:7px solid #3DD6C6}}main{{max-width:1320px;margin:28px auto;padding:0 24px}}.grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}}.kpi,.card{{background:white;border:1px solid #d8dee9;border-radius:14px;padding:18px}}.kpi b{{display:block;font-size:28px;color:#8B5CF6}}.status{{display:inline-block;padding:8px 14px;border-radius:999px;background:#17263F;color:#3DD6C6;font-weight:bold}}table{{width:100%;border-collapse:collapse;background:white;font-size:13px}}th,td{{padding:10px;border-bottom:1px solid #e8ecf2;text-align:left;vertical-align:top}}th{{background:#17263F;color:white}}code{{font-size:11px;white-space:normal}}@media(max-width:900px){{.grid{{grid-template-columns:1fr 1fr}}table{{display:block;overflow-x:auto}}}}</style></head><body><header><h1>{esc(t['title'])}</h1><p>{esc((evidence.get('project') or {}).get('name'))} · {esc(t['subtitle'])}</p></header><main><div class='status'>{esc(t['release'])}: {esc(s['release_status'])}</div><div class='grid' style='margin-top:18px'>{''.join(f'<div class="kpi"><b>{v}</b>{k}</div>' for v,k in [(s['campaign_count'],'campaigns'),(s['asset_count'],'assets'),(s['finding_count'],'findings'),(s['reviewed_finding_count'],'expert-reviewed'),(s['outcome_count'],'CG/TG rows')])}</div><section class='card' style='margin-top:20px'><b>{esc(t['warning'])}</b></section><h2>{esc(t['diagnostics'])}</h2><table><tr><th>ID</th><th>Criterion</th><th>Finding</th><th>Scope</th><th>Confidence</th><th>Expert</th><th>Evidence</th></tr>{findings}</table><h2>{esc(t['outcomes'])}</h2><table><tr><th>Campaign</th><th>Metric</th><th>CG</th><th>TG</th><th>Descriptive Δ pp</th><th>Scope</th><th>Evidence</th></tr>{outcomes}</table><h2>{esc(t['limits'])}</h2><section class='card'><ul>{limits}</ul></section></main><footer>{esc(t['warning'])}</footer></body></html>"""
    path.write_text(body, encoding="utf-8")


def render_docx(evidence: dict[str, Any], path: Path) -> None:
    t = T[evidence["locale"]]; doc = Document(); sec = doc.sections[0]; sec.orientation = WD_ORIENT.LANDSCAPE; sec.page_width, sec.page_height = sec.page_height, sec.page_width; sec.top_margin = sec.bottom_margin = Cm(1.3); sec.left_margin = sec.right_margin = Cm(1.4); doc.styles["Normal"].font.name = "Arial"; doc.styles["Normal"].font.size = Pt(9)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; r = p.add_run(t["title"]); r.bold = True; r.font.size = Pt(22); p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.add_run(f"{(evidence.get('project') or {}).get('name')}\n{t['subtitle']}"); p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.add_run(f"{t['release']}: {evidence['summary']['release_status']}").bold = True; doc.add_paragraph(t["warning"]).runs[0].bold = True
    def table(headers, rows):
        tb = doc.add_table(rows=1, cols=len(headers)); tb.style = "Table Grid"
        for i, value in enumerate(headers): tb.cell(0,i).text = value; tb.cell(0,i).paragraphs[0].runs[0].bold = True
        for row in rows:
            cells = tb.add_row().cells
            for i, value in enumerate(row): cells[i].text = clean(value, 3000)
        return tb
    s = evidence["summary"]; doc.add_heading(t["facts"], 1); table(["campaigns","assets","findings","expert-reviewed","CG/TG rows"], [[s["campaign_count"],s["asset_count"],s["finding_count"],s["reviewed_finding_count"],s["outcome_count"]]])
    experts = {item["finding_id"]: item for item in evidence["expert_assessment"]["assessments"]}; doc.add_heading(t["diagnostics"], 1); table(["Finding ID","Campaign / asset","Criterion","Finding","Confidence","Expert verdict","Evidence references"], [[f["finding_id"],f"{f['campaign_id']} / {f['creative_record_id']}",f["criterion"],f["text"],f.get("confidence"),experts.get(f["finding_id"],{}).get("verdict"),"\n".join(f["evidence_references"])] for f in evidence["agent_diagnostics"]["findings"]])
    doc.add_page_break()
    doc.add_heading(t["outcomes"], 1); table(["Campaign","Metric","CG n/rate","TG n/rate","Descriptive Δ pp","Status","Scope","Evidence"], [[o["campaign_id"],o.get("metric_label") or o.get("metric"),f"{o.get('control_n')} / {o.get('cg_rate')}",f"{o.get('test_n')} / {o.get('tg_rate')}",o.get("uplift_pp_descriptive"),o.get("evidence_status"),"campaign set","\n".join(o["evidence_references"])] for o in evidence["factual_outcomes"]["outcomes"]])
    doc.add_heading(t["expert"], 1)
    for item in evidence["expert_assessment"]["assessments"]: p = doc.add_paragraph(style="List Bullet"); p.add_run(f"{item['finding_id']} — {item['verdict']}").bold = True; p.add_run(": " + item["rationale"] if item.get("rationale") else "")
    doc.add_heading(t["limits"], 1)
    for item in evidence["limitations_and_confidence"]["limitations"]: p = doc.add_paragraph(style="List Bullet"); p.add_run(f"{item.get('code')}: ").bold = True; p.add_run(item.get("message") or "")
    doc.add_paragraph(json.dumps(evidence["limitations_and_confidence"]["confidence_summary"], ensure_ascii=False, indent=2)); doc.core_properties.author = "Arvectum"; doc.core_properties.created = doc.core_properties.modified = datetime(2000,1,1)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.docx"; doc.save(raw); normalize_office_zip(raw, path)


def render_xlsx(evidence: dict[str, Any], path: Path) -> None:
    wb = Workbook(); wb.remove(wb.active); fill = PatternFill("solid", fgColor=C["panel"]); font = Font(color=C["white"], bold=True)
    def add(name, headers, rows):
        ws = wb.create_sheet(name); ws.append(headers)
        for row in rows: ws.append(row)
        for cell in ws[1]: cell.fill = fill; cell.font = font; cell.alignment = Alignment(wrap_text=True, vertical="top")
        for row in ws.iter_rows(min_row=2):
            for cell in row: cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
        for col in range(1, len(headers)+1): ws.column_dimensions[get_column_letter(col)].width = min(max(max((len(str(ws.cell(r,col).value or "")) for r in range(1,min(ws.max_row,80)+1)), default=8)+2,11),42)
    add("Summary", ["Key","Value"], [[k,v] for k,v in evidence["summary"].items()] + [["claim_boundary",json.dumps(evidence["claim_boundary"],ensure_ascii=False)]])
    experts = {x["finding_id"]:x for x in evidence["expert_assessment"]["assessments"]}; add("Findings", ["finding_id","campaign_id","creative_record_id","criterion","score","finding","scope","confidence","expert_verdict","expert_rationale","evidence_references"], [[f["finding_id"],f["campaign_id"],f["creative_record_id"],f["criterion"],f.get("score"),f["text"],f["scope"],f.get("confidence"),experts.get(f["finding_id"],{}).get("verdict"),experts.get(f["finding_id"],{}).get("rationale")," | ".join(f["evidence_references"])] for f in evidence["agent_diagnostics"]["findings"]])
    add("CG_TG_Outcomes", ["observation_id","campaign_id","metric","control_n","test_n","cg_rate","tg_rate","descriptive_difference_pp","status","scope","individual_asset_attribution_allowed","causal_interpretation_allowed","evidence_references"], [[o["observation_id"],o["campaign_id"],o.get("metric"),o.get("control_n"),o.get("test_n"),o.get("cg_rate"),o.get("tg_rate"),o.get("uplift_pp_descriptive"),o.get("evidence_status"),"campaign_set",False,False," | ".join(o["evidence_references"])] for o in evidence["factual_outcomes"]["outcomes"]])
    add("Limitations", ["limitation_id","campaign_id","code","severity","message","context","evidence_references"], [[x.get("limitation_id"),x.get("campaign_id"),x.get("code"),x.get("severity"),x.get("message"),json.dumps(x.get("context") or {},ensure_ascii=False)," | ".join(x.get("evidence_references") or [])] for x in evidence["limitations_and_confidence"]["limitations"]])
    add("Evidence_Registry", ["reference_id","layer","scope","source_type","source_id","source_index","resolution_status"], [[key,val.get("layer"),val.get("scope"),val.get("source_type"),val.get("source_id"),val.get("source_index"),val.get("resolution_status")] for key,val in sorted(evidence["evidence_registry"].items())]); wb.properties.creator = "Arvectum"; wb.properties.created = wb.properties.modified = datetime(2000,1,1)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.xlsx"; wb.save(raw); normalize_office_zip(raw, path)


def build_report_bundle(evidence: dict[str, Any], output_dir: Path, *, clean=True) -> dict[str, Any]:
    errors = validate_evidence(evidence)
    if errors: raise ValueError("invalid report evidence: " + "; ".join(errors))
    if clean and output_dir.exists(): shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True); paths = {"html":output_dir/"client_report_v2.html","one_page_pptx":output_dir/"client_report_v2_one_page.pptx","full_pptx":output_dir/"client_report_v2_full.pptx","docx":output_dir/"client_report_v2.docx","evidence":output_dir/"client_report_v2_evidence.json","xlsx":output_dir/"client_report_v2_appendix.xlsx"}
    render_html(evidence,paths["html"]); render_one_page_pptx(evidence,paths["one_page_pptx"]); render_full_pptx(evidence,paths["full_pptx"]); render_docx(evidence,paths["docx"]); paths["evidence"].write_bytes(json_bytes(evidence)); render_xlsx(evidence,paths["xlsx"])
    artifacts = [{"artifact_type":kind,"filename":p.name,"media_type":ARTIFACT_MEDIA_TYPES[kind],"sha256":sha256_file(p),"size_bytes":p.stat().st_size} for kind,p in paths.items()]
    manifest = {"report_id":evidence.get("report_run_id") or REPORT_ID,"report_definition_id":REPORT_ID,"report_version":REPORT_VERSION,"project_id":evidence["project"].get("id"),"project_name":evidence["project"].get("name"),"locale":evidence["locale"],"input_fingerprint":evidence.get("input_fingerprint"),"generated_at":evidence["generated_at"],"summary":evidence["summary"],"artifacts":artifacts,"claim_boundary":evidence["claim_boundary"]}
    manifest_path = output_dir/"report_manifest.json"; manifest_path.write_bytes(json_bytes(manifest)); manifest["manifest"]={"filename":manifest_path.name,"media_type":"application/json","sha256":sha256_file(manifest_path),"size_bytes":manifest_path.stat().st_size}; return manifest


def validate_report_bundle(output_dir: Path) -> list[str]:
    errors=[]; manifest_path=output_dir/"report_manifest.json"
    if not manifest_path.is_file(): return ["report_manifest.json is missing"]
    try: manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: return [f"manifest is unreadable: {exc}"]
    if manifest.get("report_definition_id")!=REPORT_ID or manifest.get("report_version")!=REPORT_VERSION: errors.append("unexpected report identity or version")
    artifacts=manifest.get("artifacts") or []
    if {x.get("artifact_type") for x in artifacts}!=set(ARTIFACT_MEDIA_TYPES): errors.append("artifact set must contain all six report formats")
    for item in artifacts:
        path=output_dir/str(item.get("filename") or "")
        if not path.is_file(): errors.append(f"artifact is missing: {path.name}"); continue
        if path.stat().st_size!=item.get("size_bytes") or sha256_file(path)!=item.get("sha256"): errors.append(f"artifact integrity mismatch: {path.name}")
    evidence_item=next((x for x in artifacts if x.get("artifact_type")=="evidence"),None)
    if evidence_item:
        try: errors.extend(validate_evidence(json.loads((output_dir/evidence_item["filename"]).read_text(encoding="utf-8"))))
        except (OSError,json.JSONDecodeError) as exc: errors.append(f"evidence JSON is unreadable: {exc}")
    boundary=manifest.get("claim_boundary") or {}
    if boundary.get("causal_interpretation_allowed") is not False or boundary.get("individual_asset_outcome_attribution_allowed") is not False or boundary.get("missing_values_inferred") is not False: errors.append("claim boundary is unsafe")
    return errors
