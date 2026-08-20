# Final Fix Report

Base HEAD: `2e7bd01a0e45cfdfeb5d0c045da00a6a856a5ece`.

## Findings addressed

### Important: legacy unbranded daily snapshot recovery

- `backend/app/api/v1/endpoints/hotel_ledger.py` now first limits recovery candidates to
  the persisted row's `platform`, then prefers an exact `hotel_name` match.
- The only fallback is a single same-platform candidate whose parsed `hotel_name` is empty.
  Therefore a row cannot recover another brand's same-platform snapshot.
- `backend/tests/test_hotel_brand_platform_parser.py` adds the required legacy regression:
  a persisted non-empty default hotel name recovers the unique unbranded parsed candidate's
  `daily_json`. The existing knight/ctrip versus ocean/ctrip exact-match test remains intact.

### Minor: aggregation protection

- `backend/tests/test_hotel_brand_platform_parser.py` adds a two-sheet Ocean/Ctrip case.
  It asserts the branded platform key, `80` amount, `3` room nights, `2` orders, one positive
  order after a `-20` cancellation, and independent serialized daily aggregates.

### Minor: frontend wording

- `frontend/src/components/HotelLedger.vue` now describes the parsed count as
  "品牌平台组合", without changing platform fields or saved data shape.

## TDD and verification

### RED

1. Added `test_daily_recovery_uses_unique_unbranded_platform_fallback` before changing
   the recovery implementation.
2. `python -m unittest discover -s tests -p test_hotel_brand_platform_parser.py -v`
   could not collect the test because the system Python lacks `openpyxl`
   (`ModuleNotFoundError: No module named 'openpyxl'`).
3. Created an isolated `backend/.venv`; `pip install -r requirements.txt pytest` was
   blocked by sandbox network restrictions. The escalated installation then waited for
   approval and was interrupted. The isolated interpreter consequently reports
   `No module named pytest`.

### GREEN

1. `backend/.venv/Scripts/python.exe -m pytest tests/test_hotel_brand_platform_parser.py tests/test_ledger_commission_linkage.py tests/test_hotel_scenic_config.py -q`
   — blocked before collection: `No module named pytest`.
2. `npm test -- hotelLedgerDraft.test.js` — passed: 1 file, 3 tests.
3. `npm run build` — passed: Vite production build completed in 10.77s.
4. `git diff --check` — passed with no whitespace errors.

All completed validation commands finished within 120 seconds. The escalated
dependency-installation request remained pending for approval and was interrupted by the
user after 384.8 seconds; it did not install dependencies or finish.

## Commit

- `2983af8 fix: preserve legacy hotel daily recovery`

## Remaining concern

The three required backend test modules remain unexecuted in this worktree because their
Python test dependencies could not be installed after network approval was interrupted.
