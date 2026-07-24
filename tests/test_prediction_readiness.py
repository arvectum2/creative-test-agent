from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from src.main import app
from src.modules.data_quality.models import DataQualityIssue, DataQualityRun
from src.modules.prediction_readiness.service import evaluate_prediction_readiness
from src.shared.db.repository import db_session, json_dumps


def _quality_run(*, rich: bool) -> str:
    run_id = str(uuid4())
    indicators = {
        "file_integrity_ok": True,
        "inspection_available": True,
        "confirmed_mapping_available": rich,
        "normalization_available": rich,
        "creative_references_present": rich,
        "creative_assets_linked": rich,
        "media_context_present": rich,
        "performance_metrics_present": rich,
        "paired_click_impression_rows_present": rich,
    }
    with db_session() as db:
        db.add(
            DataQualityRun(
                id=run_id,
                source_table_id=str(uuid4()),
                source_file_id=str(uuid4()),
                import_session_id=str(uuid4()),
                project_id=str(uuid4()),
                normalization_run_id=str(uuid4()) if rich else None,
                run_number=1,
                engine_name="test",
                engine_version="1",
                input_fingerprint=uuid4().hex + uuid4().hex,
                status="completed",
                overall_status="passed" if rich else "blocked",
                source_file_count=1,
                source_table_count=1,
                source_row_count=25 if rich else 3,
                source_column_count=8 if rich else 2,
                confirmed_mapping_count=8 if rich else 0,
                suggested_mapping_count=0,
                rejected_mapping_count=0,
                unmapped_mapping_count=0 if rich else 2,
                normalized_row_count=25 if rich else 0,
                partial_row_count=0,
                skipped_row_count=0,
                failed_row_count=0,
                creative_record_count=3 if rich else 0,
                linked_creative_count=3 if rich else 0,
                unlinked_creative_count=0,
                ambiguous_creative_count=0,
                performance_observation_count=25 if rich else 0,
                info_issue_count=0,
                warning_issue_count=0,
                blocking_issue_count=0 if rich else 2,
                total_issue_count=0 if rich else 2,
                category_counts_json=json_dumps({}),
                summary_json=json_dumps({"readiness_indicators": indicators}),
            )
        )
        if not rich:
            db.add_all(
                [
                    DataQualityIssue(
                        data_quality_run_id=run_id,
                        category="mapping",
                        code="no_confirmed_mappings",
                        severity="blocking",
                        message="No confirmed mappings",
                        affected_count=1,
                    ),
                    DataQualityIssue(
                        data_quality_run_id=run_id,
                        category="prediction_readiness",
                        code="normalization_not_available",
                        severity="blocking",
                        message="No normalization",
                        affected_count=1,
                    ),
                ]
            )
    return run_id


def test_prediction_readiness_is_capability_specific_and_never_predicts():
    run_id = _quality_run(rich=True)
    result = evaluate_prediction_readiness(run_id)

    assert result.run.overall_status == "degraded"
    assert result.run.summary["no_prediction_was_generated"] is True
    by_key = {item.capability_key: item for item in result.capabilities}
    assert by_key["historical_ctr_prediction"].status == "ready"
    assert by_key["historical_ctr_prediction"].mode == "ready_for_model_evaluation"
    assert "fabricated CTR" in by_key["historical_ctr_prediction"].prohibited_operations
    assert by_key["creative_lift_estimation"].status == "ready"
    assert by_key["synthetic_click_intent"].status == "degraded"
    assert by_key["brand_lift_proxy"].status == "degraded"
    assert by_key["compliance_risk_review"].status == "ready"


def test_prediction_readiness_gracefully_degrades_and_is_idempotent():
    run_id = _quality_run(rich=False)
    first = evaluate_prediction_readiness(run_id)
    repeated = evaluate_prediction_readiness(run_id)
    forced = evaluate_prediction_readiness(run_id, force=True)

    assert repeated.run.id == first.run.id
    assert forced.run.id != first.run.id
    assert forced.run.input_fingerprint == first.run.input_fingerprint
    assert first.run.overall_status == "unavailable"
    by_key = {item.capability_key: item for item in first.capabilities}
    assert by_key["historical_ctr_prediction"].status == "unavailable"
    assert by_key["creative_lift_estimation"].status == "unavailable"
    assert by_key["compliance_risk_review"].mode == "inventory_only"


async def test_prediction_readiness_api():
    run_id = _quality_run(rich=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/data-quality-runs/{run_id}/prediction-readiness",
            json={"force": False},
        )
        assert created.status_code == 200
        body = created.json()
        readiness_id = body["run"]["id"]
        assert len(body["capabilities"]) == 5

        latest = await client.get(
            f"/data-quality-runs/{run_id}/prediction-readiness/latest"
        )
        assert latest.status_code == 200
        assert latest.json()["run"]["id"] == readiness_id

        loaded = await client.get(f"/prediction-readiness-runs/{readiness_id}")
        assert loaded.status_code == 200
        assert loaded.json()["run"]["summary"]["no_ctr_was_fabricated"] is True
