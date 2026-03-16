# Test Plan

## Backend priorities

- `routers_stock`
  - draft save/load/commit
  - correction flow for in/out records
  - export parameter validation
  - stock record detail access
- `routers_attachments`
  - attachment upload type/size validation
  - download/preview project access control
  - soft delete behavior
  - site photo aggregation
  - cleanup endpoint behavior
- `routers_progress`
  - create validation for empty task names
  - update/delete project scoping
- `routers_assets`
  - materials CRUD scoping
  - inventory delete password check
  - machine ledger list/create/update/delete
  - export endpoints
- `frontend_static`
  - built asset served when present
  - fallback to `index.html`
  - `/api/*` does not resolve to SPA fallback

## Frontend priorities

- `useProgressPlanPersistence`
  - createTask
  - updateTask
  - removeTask
  - persistRow
  - persistSortOrders
- `useMachineLedgerPhotos`
  - preview URL lifecycle
  - load edit photos
  - remove dropped existing photos
  - upload new photos with retry
- `useConstructionLogPhotos`
  - image-only filtering
  - max photo limit
  - remove photo cleanup
  - upload count and retry behavior
- Router/store/public utilities
  - route guard meta behavior
  - storage helpers
  - notify wrapper smoke coverage

## Recommended execution order

1. Backend router regression tests
2. Frontend composable unit tests
3. Page-level integration tests for highest-risk flows
