# Backend Services Conventions

This folder contains backend business services extracted from `app/main.py`.

## Purpose

- Keep route handlers in `app/main.py` thin.
- Centralize reusable business workflows.
- Reduce cross-feature coupling and regression risk.

## Current Modules

- `attachments.py`: attachment upload, naming, path safety, cleanup, normalization.
- `bootstrap_import.py`: SQLite package import and validation workflow.
- `exports.py`: HTML/Excel export builders.
- `logs_and_ledger.py`: construction logs and machine ledger business logic.
- `materials_inventory.py`: materials and inventory operations.
- `projects.py`: project deletion cascade cleanup.
- `stock_flow.py`: stock in/out, draft commit, record correction.

## Service Rules

- **Inputs**: receive domain objects and primitives (for example `Session`, `Project`, `User`, payload models).
- **Validation**: validate business constraints inside service methods and raise `HTTPException` with stable messages.
- **Side effects**: DB writes, file operations, and idempotency logic belong in services, not route functions.
- **Return shape**: keep API-compatible return shapes unchanged unless route contract is explicitly updated.
- **Boundary**: do not import route handlers from `main.py`; one-way dependency is `main.py -> services`.

## Transaction Guidance

- Keep commit/rollback ownership consistent per workflow.
- If a workflow performs multiple DB steps, handle rollback close to the failure branch.
- For file deletion/move operations, guard with safety checks and avoid escaping upload root.

## When Adding a New Service

- Add focused, feature-oriented functions (avoid generic utility dumping).
- Keep function names action-oriented (for example `create_*`, `delete_*`, `commit_*`).
- Wire through `main.py` as a thin delegation route.
- Run backend tests after changes: `python -m pytest tests -q`.
