# Operation forecasting and supply-chain closure validation

## Database migrations and concurrency

Validated on local MySQL 8.0.43 in a newly created disposable schema, using minimal legacy parent tables. Business databases were not changed. All three migrations completed twice in sequence:

- `20261010_contract_ledger_invoice_linkage.sql`
- `20261010_cash_execution_reconciliation.sql`
- `20261010_fund_alert_receipts.sql`

Verified that deleting a cash task's approval source is rejected by its foreign key and that a cash task without a source is rejected by its CHECK constraint.

Ran `tests/test_ledger_period_lock.py` against the disposable MySQL schema: **3 passed**, including actual second-session blocking while the first session holds the period lock. Removed the disposable schema after validation.

## Baseline regression

Frontend baseline: **57 files, 345 tests passed**.

Backend unittest baseline: 613 tests executed; two tests initially failed because ignored Excel fixtures were absent from the worktree. Copied the original two fixtures into the isolated worktree for testing only. The entire affected calculator module then passed **9 tests**. These fixture files are not staged.

Final full regression, browser checks and production release evidence will be recorded after remaining implementation and review.

Full pytest baseline on 2026-11-10: **744 passed, 4 failed, 2 skipped, 230 subtests passed**. Two older invoice tests still create a stub allocation table now supplied by registered metadata. Two contract organization tests omit newly required scenic/business fields. These fixture integration failures are assigned to the integrity completion task; production validation requirements are retained.

Analysis/forecast UI Task 6: **58 focused frontend tests and production build passed**, commit `69eb070`. Independent review requested fixes for actual-platform-only selection and month/custom request synchronization before release.

Server preflight on 2026-11-10: revision/release `d1ec542145c3fdb9ba32e3163781ffdbb1baaece`, backend service active, 27 GB disk available; new closure migrations not yet present. Deployment preparation does not change the running release.

Business trace: `7fe8684`, 34 focused backend and 30 frontend tests, production build passed. Independent spec/quality review approved; canonical period selection avoids mixing shared-contract records across periods.

Fund integrity completion regression on 2026-11-11: full backend **790 passed, 2 skipped, 230 subtests passed**, four existing deprecation warnings. Funds/approval frontend **32 passed**, production build passed. Final new scope and conservative-backfill tests **20 passed**. Independent review pending.

Actual local MySQL/InnoDB contention checks passed: invoice allocation holds the fund lock, concurrent stale-snapshot fund editing waits then rejects the financial change; two simultaneous 60-unit executions against a 100-unit task allow exactly one execution, leaving executed amount 60. A newly created disposable database was removed after validation. No real business database was changed.

Extended actual InnoDB validation also passed all four invoice races: manual/source invoice × amount/contract-snapshot edit. Editing establishes an earlier authentication snapshot, waits while allocation owns the parent lock, then rejects with 409 after allocation commits. Source values remain unchanged. Disposable schema removed.

Full backend after algorithm completion: **799 passed, 2 skipped, 230 subtests**, four existing deprecations. Final invoice fix focused coverage: **75 backend and 36 frontend passed**. Earlier full frontend run exposed missing route injection in old contract tests; fixed the harness and added initial/query-change contract deep-link checks. New full frontend run pending.

Full frontend regression after the harness/deep-link fixes: **60 files, 379 tests passed**, without unhandled errors. Production build passed at `c787b4c`; existing bundle-size and VueUse annotation warnings remain.

Full backend regression at `c787b4c`: **804 passed, 2 skipped, 230 subtests passed**, four existing deprecation warnings (2026-11-11). Final whole-branch review and browser acceptance are in progress; production has not yet been switched.

Actual Chromium acceptance at `c787b4c`: **7 passed (17 seconds)**, no page runtime errors. Reusable test: `frontend/e2e/operation-closure.spec.js`. Covered analysis/filtering, month/custom forecast inputs, three metrics/export, view-only controls, source-period trace navigation, work-item polling, due-alert navigation, actual map selection and completion polling. HTTP responses are deterministic fixtures; this validates real browser behavior, not production API or spreadsheet contents. Actual MySQL and backend regression evidence above covers server-side behavior.
