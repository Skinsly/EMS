# Frontend Component Reuse Guide

This project uses shared header/toolbar components to keep pages consistent and reduce duplicated template code.

## Core Reusable Components

- `components/StockHeadBar.vue`
  - Standard page-header shell for list pages
  - Slots: `actions`, `title`, `pager`
  - Default pager is built-in (`TopPager`)

- `components/TopPager.vue`
  - Unified page navigation (prev / next)
  - Props: `page`, `totalPages`
  - Emits: `prev`, `next`

- `components/ToolbarSearchInput.vue`
  - Unified toolbar search input
  - Props: `modelValue`, `placeholder`
  - Emits: `update:modelValue`, `input`, `enter`

- `components/ToolbarIconAction.vue`
  - Unified icon button with tooltip + aria label
  - Props: `tooltip`, `ariaLabel`, `type`, `disabled`
  - Emits: `click`

## Team Rules

1. Use `StockHeadBar` for all stock-style list pages.
2. Do not hand-write `top-pager` blocks in pages.
3. Use `ToolbarSearchInput` instead of ad-hoc toolbar `el-input`.
4. Use `ToolbarIconAction` for icon actions instead of repeating `el-tooltip + el-button`.
5. Keep page-specific visual fixes in scoped styles or dedicated override files.

## Style Override Rule

- Segmented title single-layer overrides for stock manage/records live in:
  - `src/styles/segment-title-fix.css`
- Avoid adding temporary global overrides to `src/styles.css` unless truly shared.

## Example

```vue
<StockHeadBar title="材料管理" :page="page" :total-pages="totalPages" @prev="prevPage" @next="nextPage">
  <template #actions>
    <ToolbarSearchInput v-model="keyword" placeholder="按名称搜索" @enter="load" />
    <ToolbarIconAction tooltip="新增" aria-label="新增" @click="openCreate">
      <Plus />
    </ToolbarIconAction>
  </template>
</StockHeadBar>
```
