# PRE-PILOT-007 acceptance

PRE-PILOT-007 считается выполненным, когда:

- пакет калибровки детерминированно создаётся одной локальной командой;
- шаблон содержит 20 creative cases и не содержит клиентских данных;
- протокол явно фиксирует, что 15–20 реальных креативов пригодны для калибровки процесса, но не для устойчивого обучения модели;
- включённый case имеет `creative_id`, исходный `source_record_id`, SHA-256 и больше не считается template evidence;
- системные findings можно оценивать поштучно, а human-added omissions и reviewer disagreements не теряются;
- завершённая adjudication требует adjudicator и rationale;
- исторические outcomes принимаются только с provenance и `causal_interpretation_allowed=false`;
- real-human и synthetic questionnaire evidence учитываются раздельно, проходят проверку арифметики counts и границ шкалы;
- workflow log разделяет wall-clock и operator touch time, а manual action count является целым неотрицательным числом;
- metric dictionary не допускает финальных thresholds до реального пилота и методологического sign-off;
- summary формирует только описательные метрики и всегда запрещает accuracy, causal lift, market-effectiveness и regulatory-approval claims;
- `methodology_review_required` возможен только после 15 реальных cases, finding-level review и завершённого workflow measurement для каждого из них;
- validator обнаруживает повреждение manifest, неверные SHA-256, неизвестные case IDs, неполные included cases, причинную интерпретацию и смешение synthetic/human evidence;
- `seal` обновляет hashes после контролируемого заполнения пакета;
- synthetic self-test содержит 15 cases, 30 finding reviews и 180 явно синтетических responses, но не имитирует реальный пилот;
- полный regression suite и отдельный PRE-PILOT-007 CI gate проходят;
- CI остаётся read-only и не коммитит generated evidence.

Не входит в acceptance:

- обучение или выбор LLM/VLM/CTR-модели;
- фиксация финальных quality thresholds;
- обещание точности;
- причинная оценка brand/creative lift;
- проведение реального опроса;
- подтверждение compliance или регуляторного соответствия;
- утверждение, что synthetic self-test является market evidence.
