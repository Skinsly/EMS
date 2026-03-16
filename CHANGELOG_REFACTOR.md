# Changelog - Refactor Track

## Current refactor batch

### Backend

- Reduced `backend/app/main.py` to a composition-focused entry.
- Moved startup/bootstrap helpers into `backend/app/startup.py`.
- Split domain routes into dedicated router modules:
  - `backend/app/routers_core.py`
  - `backend/app/routers_logs.py`
  - `backend/app/routers_progress.py`
  - `backend/app/routers_assets.py`
  - `backend/app/routers_stock.py`
  - `backend/app/routers_attachments.py`
- Introduced `backend/app/frontend_static.py` for frontend static and SPA fallback handling.
- Upgraded route modules from plain handler files to `APIRouter`-based modules.

### Frontend

- Unified notification calls through `frontend/src/utils/notify.js`.
- Unified browser storage access through `frontend/src/utils/storage.js`.
- Extracted app shell logic into `frontend/src/composables/useAppShell.js`.
- Extracted construction log photo workflow into `frontend/src/composables/useConstructionLogPhotos.js`.
- Extracted machine ledger photo workflow into `frontend/src/composables/useMachineLedgerPhotos.js`.
- Extracted progress plan persistence logic into `frontend/src/composables/useProgressPlanPersistence.js`.
- Reduced large page components by moving repeated side effects and async workflows into composables.

### Test additions

- Added frontend unit tests for key composables.
- Added backend regression coverage for router-level flows.
- Added project-level maintenance and refactor documentation.

## Suggested commit message

```text
refactor: modularize backend routers and unify frontend shared flows

Reduce the FastAPI entry file to app composition, move domain endpoints into APIRouter modules, and centralize frontend notification, storage, photo, and persistence workflows to lower maintenance cost.
```
