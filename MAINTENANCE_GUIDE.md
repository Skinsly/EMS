# Maintenance Guide

## Backend placement rules

- Put auth/bootstrap/project/file-category/project-file endpoints in `backend/app/routers_core.py`.
- Put construction log endpoints in `backend/app/routers_logs.py`.
- Put progress plan endpoints in `backend/app/routers_progress.py`.
- Put materials, inventory, machine ledger, and related exports in `backend/app/routers_assets.py`.
- Put stock flow, drafts, stock records, corrections, and stock exports in `backend/app/routers_stock.py`.
- Put attachment, preview/download, site photo, and cleanup endpoints in `backend/app/routers_attachments.py`.
- Put frontend asset/fallback behavior in `backend/app/frontend_static.py`.

## Backend coding rules

- Prefer `APIRouter` per domain.
- Keep router handlers thin; push complex logic into services.
- Reuse dependency injection patterns already in the codebase.
- If a new domain does not fit an existing router, create `backend/app/routers_<domain>.py` and register it in `backend/app/main.py`.
- Keep startup-only logic in `backend/app/startup.py`.

## Frontend placement rules

- Keep page files focused on UI state and event orchestration.
- Put repeated async workflow, upload logic, persistence logic, or reusable page behavior into `frontend/src/composables/`.
- Put shared notification logic in `frontend/src/utils/notify.js`.
- Put browser storage access in `frontend/src/utils/storage.js`.
- Use `ElMessageBox` only for confirmations; use `notify` for success/error/warning/info.

## Naming rules

- Page components: `XxxPage.vue`
- Composables: `useXxx.js`
- Backend routers: `routers_<domain>.py`
- Backend services remain domain-oriented under `backend/app/services/`

## Review checklist for new changes

- Does this new code belong in an existing router or composable?
- Is repeated storage access going through `storage`?
- Are toast notifications going through `notify`?
- Is the page file getting heavier because shared logic was not extracted?
- Is the backend entry file staying small?
