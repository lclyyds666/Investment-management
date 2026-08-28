# Task 1 Report: Unified Yuan/Wan Conversion Utilities

## Delivered

- Added `frontend/src/utils/money.js` with the shared `YUAN_PER_WAN` constant and four boundary helpers.
- `yuanToWan` accepts API values in yuan; `wanToYuan` converts UI wan values back to yuan and rounds to fen precision.
- `formatWanFromYuan` only converts and formats raw yuan values; `formatWanValue` formats values that have already been converted to wan.
- Empty, non-numeric, and non-finite inputs normalize to zero.
- Added focused Vitest coverage for exact conversion boundaries, the two separate formatting paths, and invalid input normalization.

## Validation

- Confirmed the new test initially failed because `./money` did not exist.
- `cd frontend; npm test -- --run src/utils/money.test.js` passes: 3 tests passed.
- `git diff --check` passes.

## Review

- Self-review found the implementation matches the approved interfaces and keeps the yuan-versus-wan formatting boundary explicit.
- No production call sites were changed in this task; subsequent tasks must choose `formatWanFromYuan` for API yuan values and `formatWanValue` only after conversion to wan.
