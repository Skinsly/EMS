<template>
  <div class="page-card module-page stock-manage-page">
    <StockHeadBar :title="isManageRoute ? '' : `${modeText}管理`" title-class="stock-title-segment-wrap" :page="page" :total-pages="totalPages" @prev="prevPage" @next="nextPage">
      <template #actions>
        <div class="stock-action stock-action-search">
          <ToolbarSearchInput v-model="keyword" placeholder="按名称/规格搜索" @input="page = 1" />
        </div>
        <div class="stock-action stock-action-add">
          <ToolbarIconAction :tooltip="`新增${modeText}`" :aria-label="`新增${modeText}`" @click="openAddDialog">
            <Plus />
          </ToolbarIconAction>
        </div>
        <div class="stock-action stock-action-commit">
          <ToolbarIconAction tooltip="确认入账" aria-label="确认入账" :disabled="!rows.length || commitLoading" @click="commitDraft">
            <Check />
          </ToolbarIconAction>
        </div>
        <div class="stock-action stock-action-del">
          <ToolbarIconAction tooltip="删除选中" aria-label="删除选中" type="danger" :disabled="!selectedRows.length" @click="deleteSelectedRows">
            <Delete />
          </ToolbarIconAction>
        </div>
      </template>
      <template #title>
        <template v-if="isManageRoute">
          <div class="stock-title-row">
            <el-segmented v-model="activeMode" :options="modeOptions" class="stock-dark-segment" @change="onModeChange" />
          </div>
        </template>
        <template v-else>
          {{ `${modeText}管理` }}
        </template>
      </template>
      <template #pager>
        <div class="stock-head-right">
          <div class="stock-head-draft">
            <span class="stock-head-draft-text">{{ draftStatusText }}</span>
            <el-button type="warning" size="small" :disabled="!rows.length || commitLoading" @click="commitDraft">
              {{ commitLoading ? '入账中...' : '确认入账' }}
            </el-button>
          </div>
          <TopPager :page="page" :total-pages="totalPages" @prev="prevPage" @next="nextPage" />
        </div>
      </template>
    </StockHeadBar>

    <el-table class="uniform-row-table clickable-table" :data="pagedRows" border @selection-change="onSelectionChange" @row-click="onRowClick">
      <el-table-column type="selection" width="50" />
      <el-table-column label="序号" width="70">
        <template #default="scope">{{ formatIndex(scope.$index) }}</template>
      </el-table-column>
      <el-table-column prop="date" label="日期" width="150" />
      <el-table-column label="名称" min-width="220">
        <template #default="scope">{{ getMaterial(scope.row.material_id)?.name || '' }}</template>
      </el-table-column>
      <el-table-column label="规格" min-width="160">
        <template #default="scope">{{ getMaterial(scope.row.material_id)?.spec || '' }}</template>
      </el-table-column>
      <el-table-column prop="qty" label="数量" width="130" />
      <el-table-column label="单位" width="90">
        <template #default="scope">{{ getMaterial(scope.row.material_id)?.unit || '' }}</template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="180" />
    </el-table>

    <el-dialog v-model="addDialogOpen" width="min(420px, 86vw)" class="macos-dialog stock-edit-dialog" :show-close="false" :close-on-press-escape="false">
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="addDialogOpen = false" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">{{ editingRowIndex >= 0 ? `编辑${modeText}材料` : `${modeText}材料` }}</div>
          <div class="dialog-header-actions-left">
            <el-tooltip content="确认" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="确认" @click="confirmAddRow">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>

      <el-form label-width="0" @keydown.enter.prevent="confirmAddRow">
        <el-form-item>
          <el-input v-model="draftDateInput" placeholder="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item>
          <div ref="materialFieldRef" class="material-autocomplete-field">
            <el-input v-model="draftMaterialText" placeholder="名称" @input="onDraftMaterialInput" @focus="onDraftMaterialFocus" @blur="onDraftMaterialBlur">
              <template #append>
                <el-dropdown trigger="click" @command="setDraftMaterial">
                  <span>材料</span>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item v-for="m in materials" :key="m.id" :command="m.id">
                        {{ m.name }} {{ m.spec || '' }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-input>
            <div v-if="materialSuggestOpen && draftMaterialSuggestions.length" class="material-suggest-menu" :style="{ left: `${materialSuggestLeft}px` }">
              <button v-for="item in draftMaterialSuggestions" :key="item.id" type="button" class="material-suggest-item" @mousedown.prevent="onDraftMaterialPick(item)">
                {{ item.label }}
              </button>
            </div>
          </div>
        </el-form-item>
        <el-form-item>
          <el-input-number v-model="draftRow.qty" :min="1" :precision="0" :step="1" :controls="false" placeholder="数量" style="width: 100%" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="draftRow.remark" placeholder="备注" />
        </el-form-item>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Check, Delete, Plus } from '@element-plus/icons-vue'
import ToolbarSearchInput from '../components/ToolbarSearchInput.vue'
import ToolbarIconAction from '../components/ToolbarIconAction.vue'
import StockHeadBar from '../components/StockHeadBar.vue'
import { useStockDraftPage } from '../composables/useStockDraftPage'

const props = defineProps({
  mode: { type: String, default: 'in' }
})

const modeText = computed(() => (props.mode === 'out' ? '出库' : '入库'))

const {
  isManageRoute,
  modeOptions,
  activeMode,
  onModeChange,
  materials,
  page,
  totalPages,
  prevPage,
  nextPage,
  keyword,
  rows,
  pagedRows,
  selectedRows,
  onSelectionChange,
  onRowClick,
  formatIndex,
  getMaterial,
  addDialogOpen,
  openAddDialog,
  editingRowIndex,
  draftDateInput,
  draftRow,
  draftMaterialText,
  materialFieldRef,
  materialSuggestOpen,
  draftMaterialSuggestions,
  materialSuggestLeft,
  onDraftMaterialInput,
  onDraftMaterialFocus,
  onDraftMaterialBlur,
  onDraftMaterialPick,
  setDraftMaterial,
  confirmAddRow,
  deleteSelectedRows,
  draftStatusText,
  commitLoading,
  commitDraft
} = useStockDraftPage(props.mode)
</script>

<style scoped>
.stock-head-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.stock-head-draft {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.stock-head-draft-text {
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
}

.stock-action {
  display: inline-flex;
  align-items: center;
}

.stock-action-commit {
  display: none;
}

.stock-title-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.stock-title-commit {
  display: none;
}

.stock-manage-page :deep(.stock-page-head .stock-page-pager) {
  width: auto;
}

.stock-manage-page :deep(.stock-page-head .stock-page-title.stock-title-segment-wrap) {
  pointer-events: none;
}

.stock-manage-page :deep(.stock-page-head .stock-page-title.stock-title-segment-wrap .stock-dark-segment),
.stock-manage-page :deep(.stock-page-head .stock-page-title.stock-title-segment-wrap .stock-dark-segment .el-segmented__item) {
  pointer-events: auto;
}

.material-autocomplete-field {
  position: relative;
  width: 100%;
}

.material-suggest-menu {
  position: absolute;
  top: calc(100% + 6px);
  min-width: 190px;
  max-width: calc(100% - 10px);
  background: var(--panel-solid);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 14px 24px rgba(15, 23, 42, 0.12);
  z-index: 50;
  max-height: 220px;
  overflow-y: auto;
  overflow-x: hidden;
}

.material-suggest-item {
  width: 100%;
  border: none;
  background: transparent;
  text-align: left;
  padding: 8px 10px;
  color: var(--text);
  cursor: pointer;
}

.material-suggest-item:hover {
  background: color-mix(in srgb, var(--panel-soft) 84%, transparent);
}

@media (max-width: 900px) {
  .stock-head-draft {
    display: none !important;
  }

  .stock-action-commit {
    display: inline-flex;
  }
}
</style>
