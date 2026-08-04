"""Human sign-off checklist template for PRE-PILOT-006."""

from __future__ import annotations

from typing import Any

REHEARSAL_ID = "PRE-PILOT-006"
REHEARSAL_VERSION = "1.0.0"


def blank_operator_checklist() -> dict[str, Any]:
    tasks = [
        ("OP-01", "Confirm the rehearsal workspace contains no client data and the server is stopped."),
        ("OP-02", "Run the documented command without developer assistance."),
        ("OP-03", "Open rehearsal_manifest.json and identify the overall automated status."),
        ("OP-04", "Locate the original import, data-review XLSX and provisional one-page PPTX/HTML artifacts."),
        ("OP-05", "Validate the primary backup with scripts/check_backup.py."),
        ("OP-06", "Identify the pre-restore backup and explain why it exists."),
        ("OP-07", "Start the restored local application using the rehearsal workspace configuration."),
        ("OP-08", "Find the restored project and trace one report statement to its source evidence."),
        ("OP-09", "Download the restored PPTX and confirm that unavailable/degraded capabilities remain labelled."),
        ("OP-10", "Record blockers, assistance requested, elapsed time and final operator decision."),
    ]
    return {
        "rehearsal_id": REHEARSAL_ID,
        "rehearsal_version": REHEARSAL_VERSION,
        "automated_drill_is_human_signoff": False,
        "operator": "",
        "observer": "",
        "started_at": None,
        "completed_at": None,
        "assistance_requested": None,
        "elapsed_minutes": None,
        "final_decision": "not_started",
        "allowed_final_decisions": [
            "passed",
            "passed_with_observations",
            "repeat_required",
            "blocked",
        ],
        "tasks": [
            {
                "task_id": task_id,
                "instruction": instruction,
                "status": "not_started",
                "allowed_statuses": [
                    "not_started",
                    "passed",
                    "failed",
                    "not_applicable",
                ],
                "evidence": "",
                "observation": "",
            }
            for task_id, instruction in tasks
        ],
        "blockers": [],
        "notes": "",
    }
