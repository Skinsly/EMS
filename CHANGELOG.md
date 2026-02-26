# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- Added reusable frontend components:
  - `StockHeadBar`
  - `TopPager`
  - `ToolbarSearchInput`
  - `ToolbarIconAction`
- Added `src/styles/segment-title-fix.css` to isolate segmented-title single-layer overrides.
- Added `frontend/src/styles/base.css` to separate base theme variables from main stylesheet.
- Added frontend reuse guide: `frontend/src/component-reuse-guidelines.md`.
- Added backend regression tests covering bootstrap/auth, project lifecycle, material scoping, stock in/out inventory changes, stock draft commit flow, and stock record correction flow.
- Added backend smoke flow test: `backend/tests/test_smoke_flow.py` (login/project/material/stock-in/correct/inventory).
- Added one-click Windows smoke script: `scripts/smoke.bat`.
- Added full release-check smoke script: `scripts/smoke-full.bat`.

### Changed
- Refactored multiple pages to reuse shared header/toolbar/pager components without changing business behavior.
- Simplified `SitePhotosPage` rendering by removing obsolete grouped wrapper logic.
- Normalized several toolbar tooltip/aria labels for consistency.
- Rewrote and simplified `README.md` for clearer GitHub onboarding.

### Fixed
- Fixed segmented title overlay/double-layer rendering in stock manage/records pages.
- Fixed multiple mobile/desktop layout consistency issues in page headers and table sections.
- Fixed construction-log index button hover cursor (`pointer`).
- Fixed SQLite decimal binding issue in stock in/out inventory updates by normalizing SQL parameters.
- Fixed project deletion cleanup gap by deleting machine ledger rows and related attachments when deleting a project.
- Fixed machine-ledger delete flow to soft-delete and clean related attachments.
- Fixed idempotency edge case where blank `X-Idempotency-Key` could reuse cached stock-in/out responses.
- Fixed several frontend duplicate-submit risks by adding loading locks on project create/delete, stock-record correction, construction-log save/delete, and machine-ledger save/delete actions.

### Removed
- Removed unused legacy toolbar/mobile style blocks from `styles.css`.
- Removed dead style fragments no longer referenced after header/toolbar refactor.
