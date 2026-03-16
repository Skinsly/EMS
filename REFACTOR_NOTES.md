# Refactor Notes

## What changed

- Backend entry has been reduced to app wiring in `backend/app/main.py`.
- Backend routes are split by domain and mounted with `APIRouter`:
  - `backend/app/routers_core.py`
  - `backend/app/routers_logs.py`
  - `backend/app/routers_progress.py`
  - `backend/app/routers_assets.py`
  - `backend/app/routers_stock.py`
  - `backend/app/routers_attachments.py`
- Frontend shared behavior is centralized in utils/composables:
  - `frontend/src/utils/notify.js`
  - `frontend/src/utils/storage.js`
  - `frontend/src/composables/useAppShell.js`
  - `frontend/src/composables/useConstructionLogPhotos.js`
  - `frontend/src/composables/useMachineLedgerPhotos.js`
  - `frontend/src/composables/useProgressPlanPersistence.js`

## Why it changed

- Reduce maintenance pressure from oversized page and entry files.
- Make future features land in predictable modules.
- Centralize repeated logic for notifications, storage, photo workflows, and persistence.
- Keep the backend entry focused on composition instead of business implementation.

## Current backend structure

- `backend/app/main.py`: app creation, middleware, router registration, health endpoint, database export, frontend static registration.
- `backend/app/startup.py`: lifespan, directory creation, schema patching, seed/bootstrap startup tasks.
- `backend/app/frontend_static.py`: SPA fallback and PWA/static asset serving.
- `backend/app/routers_core.py`: auth, bootstrap, projects, file categories, project files.
- `backend/app/routers_logs.py`: construction logs.
- `backend/app/routers_progress.py`: progress plans.
- `backend/app/routers_assets.py`: materials, inventory, machine ledger, related exports.
- `backend/app/routers_stock.py`: stock in/out, drafts, stock records, correction, export.
- `backend/app/routers_attachments.py`: attachments, previews/downloads, site photos, cleanup.

## Current frontend structure

- Pages keep UI state and user interaction orchestration.
- Shared domain logic is extracted into composables.
- Notification calls go through `notify`.
- Storage calls go through `storage`.

## Suggested next maintenance focus

- Add regression tests for each router module.
- Add unit tests for new frontend composables.
- Keep new business logic out of page files unless it is strictly view-only.
