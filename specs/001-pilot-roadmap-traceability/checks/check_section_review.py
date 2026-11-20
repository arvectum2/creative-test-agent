"""Pinned source review; structural only, not product acceptance or task admission."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
DIR="specs/001-pilot-roadmap-traceability"
PIN="aeae858fae079ed681eedfc4e35462747e5ea412"
PRIOR="d5b4843107ef72d93187fa6a5b3f09d86a967f14"
MODE="client_gate"
SOURCES=json.loads("[{\"path\":\"docs/roadmap/CREATIVE_TEST_AGENT_CANONICAL_ROADMAP_v2.4_2026-08-04.md\",\"sha256\":\"1772e5eda45b0de1b729fd939c660fd48f3037890f4edef92bd8b3803283eba4\"},{\"path\":\"docs/roadmap/CURRENT.md\",\"sha256\":\"ea202580df437be41711e650c726ee6734e1c0fdc002d39410dc1358222116f3\"},{\"path\":\"docs/roadmap/WAITING_FOR_CLIENT_DATA_PLAN.md\",\"sha256\":\"8519d0b3d39ff32ad5a706e97aefeb14f85fa20967ac2fb47e643d920e0ae329\"}]")
GATES=json.loads("[{\"id\":\"REVIEW-01\",\"source\":\"docs/roadmap/CREATIVE_TEST_AGENT_CANONICAL_ROADMAP_v2.4_2026-08-04.md\",\"first_line\":95,\"last_line\":117,\"label\":\"Controlled pilot and on-prem release\",\"rule\":\"Preserve real client inputs, independent review and outcome linkage gates.\"},{\"id\":\"REVIEW-02\",\"source\":\"docs/roadmap/CREATIVE_TEST_AGENT_CANONICAL_ROADMAP_v2.4_2026-08-04.md\",\"first_line\":157,\"last_line\":164,\"label\":\"CTA-PILOT-PREP-003\",\"rule\":\"Verify all eight synthetic rehearsal checks; no validated accuracy claim.\"},{\"id\":\"REVIEW-03\",\"source\":\"docs/roadmap/CREATIVE_TEST_AGENT_CANONICAL_ROADMAP_v2.4_2026-08-04.md\",\"first_line\":168,\"last_line\":176,\"label\":\"CTA-RELEASE-PREP-001\",\"rule\":\"Recorded completion and local PASS remain scoped; reconcile with older CURRENT pointer, not actual client deployment.\"},{\"id\":\"REVIEW-04\",\"source\":\"docs/roadmap/CREATIVE_TEST_AGENT_CANONICAL_ROADMAP_v2.4_2026-08-04.md\",\"first_line\":180,\"last_line\":185,\"label\":\"CTA-CLIENT-001\",\"rule\":\"Preserve all six package criteria; no actual client data.\"}]")
def scan(raw):
    out=[];heading=0;fence=False
    for i,l in enumerate(raw.decode("utf-8").splitlines(),1):
        if not l.strip():continue
        if l.lstrip().startswith(("\x60\x60\x60","~~~")):
            fence=not fence;kind="format"
        elif fence:kind="code"
        elif re.match(r"^#{1,6}\s",l):heading=i;kind="heading"
        elif re.fullmatch(r"\s*\|?\s*[:\-]+(?:\s*\|\s*[:\-]+)+\s*\|?\s*",l) or re.fullmatch(r"\s*[-*_]{3,}\s*",l):kind="format"
        elif re.match(r"^\s*\|",l):kind="table"
        elif re.match(r"^\s*(?:[-*+]|\d+[.)])\s+",l):kind="list"
        else:kind="prose"
        out.append([i,heading,kind])
    return out
def validate(data,original,prior,current):
    errors=[]
    if data.get("schema")!="arvectum.source-section-review/1" or data.get("source_commit")!=PIN or data.get("review_baseline")!=PRIOR or data.get("mode")!=MODE or data.get("actual_acceptance_verified") is not False or data.get("execution_authorized") is not False:errors.append("scope/authority")
    if data.get("gates") is None: return errors+["missing gates"]
    src=data.get("sources",[]);paths=[s["path"] for s in src]
    if paths!=[s["path"] for s in SOURCES]:return errors+["source coverage"]
    for a,s in zip(src,SOURCES):
        p=s["path"];b=original[p]
        if hashlib.sha256(b).hexdigest()!=s["sha256"] or a.get("sha256")!=s["sha256"]:errors.append("source hash "+p)
        if not prior[p].startswith(b) or prior[p]!=current[p]:errors.append("unreviewed source change "+p)
        if a.get("rows")!=scan(b):errors.append("line/heading coverage "+p)
    rows=data["gates"]
    if len(rows)!=len(GATES):errors.append("gate coverage")
    for row,g in zip(rows,GATES):
        if any(row.get(k)!=v for k,v in g.items()):errors.append("gate identity/scope")
        if row.get("review_state") not in {"unverified","verified"}:errors.append("state")
        if row.get("review_state")=="verified":
            ev=row.get("evidence",[])
            if not ev or any(e.get("criterion")!=row["id"] or e.get("outcome")!="pass" or not re.fullmatch(r"[a-f0-9]{64}",e.get("artifact_sha256","")) or not e.get("receipt_ref") or not e.get("review_ref") for e in ev):errors.append("missing criterion-specific evidence "+row["id"])
    return errors
def inputs():
    def read(ref,p):return subprocess.check_output(["git","-C",str(ROOT),"show",ref+":"+p])
    original={s["path"]:read(PIN,s["path"]) for s in SOURCES}
    prior={p:read(PRIOR,p) for p in original}
    current={p:(ROOT/p).read_bytes() for p in original}
    return json.loads((ROOT/DIR/"section-review.json").read_text()),original,prior,current
if __name__=="__main__":
    errors=validate(*inputs())
    if errors:raise SystemExit("\n".join(errors))
    print("Structural source/section coverage PASS; no actual acceptance or authority.")
