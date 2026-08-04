# CTA-RUNTIME-002 — Graceful Shutdown Completion Acceptance

Статус: `DONE`  
Issue: `#78`  
Implementation PR: `#86`  
GitHub acceptance head: `279146903a04f24f36c3b496ce6a958ab0feaf4a`  
Close-out main: `36031f8a182cb07a9645744e4fc25aa062d42ba6`  
Execution mode: `HYBRID`  
Зависимость: `CTA-MODEL-001 — DONE`

## Scope

Задача устраняет ложный первый `FAIL` при асинхронном завершении MLX runtime. Один `stop` должен дождаться завершения PID и process group в течение grace period, применять force-kill только после него и подтвердить освобождение loopback-порта, удаление PID record и нулевой residual process count.

## GitHub acceptance

- [x] shutdown polling учитывает PID, process group и endpoint port;
- [x] финальное observation выполняется после окончания каждого timeout;
- [x] force-kill запускается только после graceful timeout;
- [x] PID ownership привязан к component/process group/profile SHA-256;
- [x] PID record удаляется только после verified shutdown;
- [x] unknown listener без PID record не убивается;
- [x] delayed graceful shutdown regression проходит;
- [x] force-kill timing regression проходит;
- [x] CTA-MODEL-001 profile contract и full CI проходят;
- [x] operator documentation и OpenCode ТЗ обновлены.

GitHub evidence на implementation head:

- `CTA-MODEL-001 profile contract`, run `#124`: `PASS`;
- repository `CI`, run `#413`: `PASS`;
- synthetic shutdown regression: `4 passed`;
- frozen model identities, revisions и dependency pins не изменены.

## Local Mac mini acceptance

- [x] frozen profile validation PASS;
- [x] exact MLX runtime/dependency pins unchanged;
- [x] one stop per normal lifecycle, minimum 3 cycles;
- [x] warm/delayed MLX lifecycle PASS with one stop;
- [x] ports 8091 and 8093 free after every stop;
- [x] PID files removed after exit;
- [x] residual process count 0;
- [x] no premature FAIL;
- [x] no client data, model weights, local paths or runtime logs committed;
- [x] sanitized evidence posted to issue #78.

Local Mac mini evidence (main `36031f8`):

- synthetic delayed-shutdown regression: 5/5 PASS;
- real MLX normal lifecycle: 3/3 PASS, один stop на цикл (llm ≈0.53s, vision ≈0.27s, force-kill не использован);
- warm/delayed lifecycle: PASS с одним stop после VLM/LLM smoke;
- premature FAIL: 0;
- force-kill on normal path: 0/3;
- ports после каждого stop: 8091/8093 free; PID files removed; residual 0;
- targeted tests: 22 PASS;
- GitHub CI на `36031f8`: все applicable workflows success.

## Close-out rule

Issue #78 и статус roadmap переводятся в `DONE` только после прохождения реального Mac mini lifecycle acceptance. Local PASS подтверждён; close-out зафиксирован status-only PR на main `36031f8`.

## Claim boundary

CTA-RUNTIME-002 proves only lifecycle reliability of the frozen local runtime contract. It does not establish validated model accuracy, causal brand lift or numeric uplift prediction.

Local instructions: `docs/local/CTA-RUNTIME-002_MAC_MINI_OPENCODE.md`.
