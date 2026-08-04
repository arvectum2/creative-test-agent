# CTA-RUNTIME-002 — Graceful Shutdown Completion Acceptance

Статус: `GITHUB ACCEPTED / BLOCKED_LOCAL`  
Issue: `#78`  
Implementation PR: `#86`  
GitHub acceptance head: `279146903a04f24f36c3b496ce6a958ab0feaf4a`  
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

- [ ] frozen profile validation PASS;
- [ ] exact MLX runtime/dependency pins unchanged;
- [ ] one stop per normal lifecycle, minimum 3 cycles;
- [ ] warm/delayed MLX lifecycle PASS with one stop;
- [ ] ports 8091 and 8093 free after every stop;
- [ ] PID files removed after exit;
- [ ] residual process count 0;
- [ ] no premature FAIL;
- [ ] no client data, model weights, local paths or runtime logs committed;
- [ ] sanitized evidence posted to issue #78.

## Close-out rule

Issue #78 и статус roadmap нельзя переводить в `DONE` до прохождения реального Mac mini lifecycle acceptance. После local PASS создаётся отдельный status-only close-out PR с обезличенной записью результата.

## Claim boundary

CTA-RUNTIME-002 proves only lifecycle reliability of the frozen local runtime contract. It does not establish validated model accuracy, causal brand lift or numeric uplift prediction.

Local instructions: `docs/local/CTA-RUNTIME-002_MAC_MINI_OPENCODE.md`.
