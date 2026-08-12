# Scenic Hotel Config Linkage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every new hotel-ledger parse and save use the selected scenic area's persisted rate configuration instead of `0.90/0.94/0.06` constants.

**Architecture:** The hotel parse endpoint resolves the effective scenic configuration and passes an immutable rate snapshot into the parser. The parser returns that snapshot per platform; a tested frontend mapper carries it through the draft and save payload so the existing backend snapshot columns remain authoritative for historical rows.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, openpyxl, Vue 3, Vitest

## Global Constraints

- Reuse the existing persisted scenic configuration and do not add database columns.
- Do not expose or make platform formulas configurable.
- Do not recalculate historical ledgers.
- Keep hotel fee algorithm 1/2 and the fixed per-night fee behavior unchanged.

---

### Task 1: Backend hotel parse configuration snapshot

**Files:**
- Modify: `backend/app/api/v1/endpoints/hotel_ledger.py`
- Modify: `backend/app/services/hotel_ledger.py`
- Modify: `backend/app/schemas/hotel_ledger.py`
- Test: `backend/tests/test_hotel_scenic_config.py`

**Interfaces:**
- Consumes: `get_effective_config(db, scenic_id) -> EffectiveScenicConfig`
- Produces: `parse_hotel_file(..., scenic_id, rate_hexiao, rate_settle, commission_rate)` and parsed platform fields `rate_hexiao`, `rate_settle`, `commission_rate`

- [ ] **Step 1: Write failing service and endpoint tests**

```python
parsed = hotel_ledger.parse_hotel_file(
    workbook,
    scenic_id="fuzhou-ouleb",
    rate_hexiao=Decimal("0.91"),
    rate_settle=Decimal("0.95"),
    commission_rate=Decimal("0.08"),
)
assert parsed["platforms"][0]["suggested_commission"] == Decimal("3.00")
assert parsed["platforms"][0]["rate_hexiao"] == Decimal("0.91")
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `python -m unittest tests.test_hotel_scenic_config -v`

Expected: failure because `parse_hotel_file` does not accept or return scenic rate configuration.

- [ ] **Step 3: Pass the effective configuration through the endpoint and parser**

```python
config = get_effective_config(db, sid)
info = await run_in_threadpool(
    hl_svc.parse_hotel_file,
    content,
    fname,
    scenic_id=sid,
    rate_hexiao=config.ticket_rate_hexiao,
    rate_settle=config.ticket_rate_settle,
    commission_rate=config.ticket_commission_rate,
)
```

- [ ] **Step 4: Return explicit rate snapshot fields and use them in daily defaults**

```python
defs = daily_defaults(
    plat,
    d["daily"],
    rate_hexiao=rate_hexiao,
    rate_settle=rate_settle,
    commission_rate=commission_rate,
)
```

- [ ] **Step 5: Run the focused backend test**

Run: `python -m unittest tests.test_hotel_scenic_config -v`

Expected: PASS.

### Task 2: Frontend snapshot propagation

**Files:**
- Create: `frontend/src/utils/hotelLedgerDraft.js`
- Create: `frontend/src/utils/hotelLedgerDraft.test.js`
- Modify: `frontend/src/components/HotelLedger.vue`

**Interfaces:**
- Consumes: hotel parse API response with per-platform `commission_rate`, `rate_hexiao`, and `rate_settle`
- Produces: draft rows and save rows that preserve those exact values

- [ ] **Step 1: Write a failing mapper test**

```javascript
expect(createHotelDraftRows(parsed, '测试酒店')[0]).toMatchObject({
  commission_rate: 0.08,
  rate_hexiao: 0.91,
  rate_settle: 0.95
})
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `npm test -- --run src/utils/hotelLedgerDraft.test.js`

Expected: failure because the mapper does not exist.

- [ ] **Step 3: Implement draft and save mapping functions**

```javascript
export function createHotelSaveRows(draftRows) {
  return draftRows.map((row) => ({
    ...snapshotFields(row),
    commission_rate: Number(row.commission_rate),
    rate_hexiao: Number(row.rate_hexiao),
    rate_settle: Number(row.rate_settle)
  }))
}
```

- [ ] **Step 4: Replace component constants with row snapshot values**

Use `row.rate_hexiao` for previews and the mapper output for save requests. Keep `fee_per_night=44` unchanged.

- [ ] **Step 5: Run the focused frontend test**

Run: `npm test -- --run src/utils/hotelLedgerDraft.test.js`

Expected: PASS.

### Task 3: Regression, release, and production verification

**Files:**
- Verify all modified files

**Interfaces:**
- Consumes: completed backend and frontend changes
- Produces: tested commit, pushed `origin/main`, and verified production deployment

- [ ] **Step 1: Run backend regression tests**

Run: `python -m unittest tests.test_hotel_scenic_config tests.test_scenic_config tests.test_ticket_ledger_ctrip_parser tests.test_scenic_ledger_calculator tests.test_ledger_commission_linkage`

- [ ] **Step 2: Run frontend tests and production build**

Run: `npm test -- --run`

Run: `npm run build`

- [ ] **Step 3: Review the diff and whitespace**

Run: `git diff --check`

Run: `git diff --stat`

- [ ] **Step 4: Commit and push**

```bash
git add -- docs/superpowers/specs/2026-08-07-scenic-hotel-config-linkage-design.md docs/superpowers/plans/2026-08-07-scenic-hotel-config-linkage.md backend frontend
git commit -m "fix: apply scenic config to hotel ledgers"
git push origin HEAD:main
```

- [ ] **Step 5: Deploy and verify**

Deploy the committed backend application and frontend build with the repository's existing production release procedure, restart `sd-scm-backend.service`, then verify the deployed revision, service health, portal routes, and a read-only effective-config/parse calculation for `fuzhou-ouleb`.
