from uuid import uuid4

from httpx import ASGITransport, AsyncClient
import pytest

from src.main import app
from src.modules.creative_assets.models import CreativeAsset
from src.modules.quantitative_surveys.schemas import (
    CreateQuestionnaireRequest,
    CreateStudyRequest,
    QuestionConfig,
    SimulateStudyRequest,
)
from src.modules.quantitative_surveys.service import (
    close_study,
    create_questionnaire,
    create_study,
    publish_questionnaire,
    simulate_study,
    study_results,
)
from src.shared.db.repository import db_session
from src.shared.errors import AppError


def _assets(project_id: str):
    ids = [str(uuid4()), str(uuid4())]
    with db_session() as db:
        db.add_all(
            [
                CreativeAsset(
                    id=ids[0],
                    title="Banner A",
                    asset_type="image",
                    original_filename="banner-a.png",
                    project_id=project_id,
                ),
                CreativeAsset(
                    id=ids[1],
                    title="Banner B",
                    asset_type="image",
                    original_filename="banner-b.png",
                    project_id=project_id,
                ),
            ]
        )
    return ids


def _questionnaire(project_id: str):
    return create_questionnaire(
        CreateQuestionnaireRequest(
            project_id=project_id,
            name="Banner quantitative test",
            locale="en",
            randomize_questions=True,
            questions=[
                QuestionConfig(
                    code="click",
                    prompt="How likely are you to click?",
                    question_type="likert",
                    metric_key="click_intent",
                    scale_min=1,
                    scale_max=7,
                    low_label="Very unlikely",
                    high_label="Very likely",
                ),
                QuestionConfig(
                    code="fit",
                    prompt="How well does the creative fit the brand?",
                    question_type="likert",
                    metric_key="brand_fit",
                    scale_min=1,
                    scale_max=7,
                ),
                QuestionConfig(
                    code="trust",
                    prompt="Does the message feel trustworthy?",
                    question_type="yes_no",
                    metric_key="trust",
                ),
            ],
        )
    )


def test_quantitative_questionnaire_and_explicit_synthetic_results():
    project_id = str(uuid4())
    asset_ids = _assets(project_id)
    questionnaire = publish_questionnaire(_questionnaire(project_id).id)
    study = create_study(
        CreateStudyRequest(
            project_id=project_id,
            questionnaire_id=questionnaire.id,
            name="Synthetic pilot",
            target_response_count=20,
            creative_asset_ids=asset_ids,
            randomize_creatives=False,
            seed=11,
        )
    )

    created = simulate_study(
        study.id,
        SimulateStudyRequest(
            respondent_count=20,
            seed=11,
            creative_effects={asset_ids[0]: 0.8, asset_ids[1]: -0.8},
        ),
    )
    assert len(created) == 20
    assert all(item.source == "synthetic" for item in created)

    closed = close_study(study.id)
    assert closed.status == "closed"
    assert closed.response_count == 20

    results = study_results(study.id)
    assert results.total_responses == 20
    assert results.source_counts == {"synthetic": 20}
    assert {"click_intent", "brand_fit", "trust"} <= set(results.metric_keys)
    click = next(item for item in results.question_results if item["metric_key"] == "click_intent")
    assert click["by_creative"][asset_ids[0]]["mean"] > click["by_creative"][asset_ids[1]]["mean"]
    assert "Synthetic responses are labelled" in results.interpretation_notes[0]


def test_quantitative_questionnaire_rejects_qualitative_free_text():
    with pytest.raises(AppError) as error:
        create_questionnaire(
            CreateQuestionnaireRequest(
                project_id=str(uuid4()),
                name="Invalid qualitative form",
                questions=[
                    QuestionConfig(
                        code="open",
                        prompt="Tell us what you think",
                        question_type="text",
                        metric_key="message_clarity",
                    )
                ],
            )
        )
    assert error.value.code == "unsupported_question_type"


async def test_quantitative_survey_api_flow():
    project_id = str(uuid4())
    asset_ids = _assets(project_id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        questionnaire = await client.post(
            "/quantitative-questionnaires",
            json={
                "project_id": project_id,
                "name": "API quantitative test",
                "questions": [
                    {
                        "code": "click",
                        "prompt": "Likelihood to click",
                        "question_type": "likert",
                        "metric_key": "click_intent",
                        "scale_min": 1,
                        "scale_max": 5,
                    },
                    {
                        "code": "recall",
                        "prompt": "Would you remember the brand?",
                        "question_type": "yes_no",
                        "metric_key": "brand_recall",
                    },
                ],
            },
        )
        assert questionnaire.status_code == 200
        questionnaire_id = questionnaire.json()["id"]
        published = await client.post(f"/quantitative-questionnaires/{questionnaire_id}/publish")
        assert published.status_code == 200

        study = await client.post(
            "/quantitative-studies",
            json={
                "project_id": project_id,
                "questionnaire_id": questionnaire_id,
                "name": "API study",
                "target_response_count": 6,
                "creative_asset_ids": asset_ids,
                "seed": 5,
            },
        )
        assert study.status_code == 200
        study_id = study.json()["id"]

        simulated = await client.post(
            f"/quantitative-studies/{study_id}/simulate",
            json={"respondent_count": 6, "seed": 5},
        )
        assert simulated.status_code == 200
        assert len(simulated.json()) == 6

        closed = await client.post(f"/quantitative-studies/{study_id}/close")
        assert closed.status_code == 200
        assert closed.json()["response_count"] == 6

        results = await client.get(f"/quantitative-studies/{study_id}/results")
        assert results.status_code == 200
        assert results.json()["total_responses"] == 6
        assert results.json()["source_counts"]["synthetic"] == 6
