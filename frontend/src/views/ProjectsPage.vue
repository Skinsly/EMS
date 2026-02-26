<template>
  <div class="project-entry-wrap">
    <div class="page-card project-entry-card">
      <div class="toolbar project-toolbar">
        <div class="project-toolbar-left">
          <el-tooltip content="新建工程" placement="bottom">
            <el-button type="primary" @click="openCreateDialog" aria-label="新建工程">
              <el-icon><Plus /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="删除选中工程" placement="bottom">
            <el-button type="danger" :disabled="!selectedProjects.length" @click="openDeleteSelected" aria-label="删除选中工程">
              <el-icon><Delete /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
        <div class="project-toolbar-title-center">工程管理</div>
        <div class="toolbar-spacer"></div>
        <div class="project-toolbar-right">
          <el-tooltip content="退出系统" placement="bottom">
            <el-button circle type="danger" @click="logout" aria-label="退出系统">
              <el-icon><SwitchButton /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </div>

      <el-table class="clickable-table projects-table" :data="projects" border stripe style="margin-top: 12px" @row-click="enterProject" @selection-change="onProjectSelectionChange">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="name" label="工程名称" min-width="220" />
        <el-table-column prop="start_date" label="开工时间" width="160" />
      </el-table>
    </div>

    <el-dialog
      v-model="open"
      width="520px"
      class="macos-dialog project-entry-dialog"
      modal-class="project-entry-overlay"
      :fullscreen="isMobileDialog"
      :show-close="false"
      align-center
    >
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="open = false" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">新建工程</div>
          <div class="dialog-header-actions-left">
            <el-tooltip content="确认" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="确认" :disabled="creating" @click="createProject">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>
      <el-form label-width="0" @keydown.enter.prevent="createProject">
        <el-form-item>
          <el-input v-model="form.name" placeholder="请输入工程名称" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="startDateInput" placeholder="YYYY-MM-DD" />
        </el-form-item>
      </el-form>
    </el-dialog>

    <el-dialog
      v-model="deleteOpen"
      width="520px"
      class="macos-dialog project-entry-dialog"
      modal-class="project-entry-overlay"
      :fullscreen="isMobileDialog"
      :show-close="false"
      align-center
    >
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="deleteOpen = false" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">删除工程</div>
          <div class="dialog-header-actions-left">
            <el-tooltip content="确认删除" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="确认删除" :disabled="deleting" @click="deleteProject">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>
      <el-alert
        :title="`删除工程后不可恢复（当前选中 ${selectedProjects.length} 个），请输入登录密码，并输入确认短语：${ackPhrase}`"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-form label-width="0" style="margin-top: 12px" @keydown.enter.prevent="deleteProject">
        <el-form-item>
          <el-input :model-value="selectedProjectNames" placeholder="选中工程" disabled />
        </el-form-item>
        <el-form-item>
          <el-input v-model="deleteForm.password" show-password placeholder="请输入当前登录密码" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="deleteForm.confirm_text" placeholder="请输入确认短语" />
        </el-form-item>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Delete, Plus, SwitchButton } from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../store'
import { formatDateInput } from '../utils/date'

const router = useRouter()
const auth = useAuthStore()

const open = ref(false)
const deleteOpen = ref(false)
const isMobileDialog = ref(false)
const creating = ref(false)
const deleting = ref(false)
const projects = ref([])
const selectedProjects = ref([])
const form = reactive({
  name: '',
  start_date: ''
})

const startDateInput = computed({
  get: () => form.start_date,
  set: (value) => {
    form.start_date = formatDateInput(value)
  }
})
const deleteForm = reactive({
  password: '',
  confirm_text: ''
})
const ackPhrase = '我已知晓删除后不可恢复'

const loadProjects = async () => {
  const { data } = await api.get('/projects')
  projects.value = data
  selectedProjects.value = []
}

const enterProject = (project) => {
  if (!project) return
  auth.setProject(project)
  ElMessage.success(`已切换到工程: ${project.name}`)
  router.push('/construction-logs')
}

const openDeleteSelected = () => {
  if (!selectedProjects.value.length) return
  deleteForm.password = ''
  deleteForm.confirm_text = ''
  deleteOpen.value = true
}

const onProjectSelectionChange = (items) => {
  selectedProjects.value = items
}

const selectedProjectNames = computed(() => {
  if (!selectedProjects.value.length) return ''
  return selectedProjects.value.map((p) => p.name).join('、')
})

const formatDate = (d) => {
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

const openCreateDialog = () => {
  form.name = ''
  form.start_date = formatDate(new Date())
  open.value = true
}

const onCloseAllDialogs = () => {
  open.value = false
  deleteOpen.value = false
}

const updateMobileDialog = () => {
  isMobileDialog.value = window.matchMedia('(max-width: 900px)').matches
}

const createProject = async () => {
  if (creating.value) return
  if (!form.name.trim()) {
    ElMessage.error('请填写工程名称')
    return
  }
  creating.value = true
  try {
    await api.post('/projects', {
      name: form.name,
      start_date: form.start_date || ''
    })
    ElMessage.success('工程创建成功')
    open.value = false
    form.name = ''
    form.start_date = ''
    await loadProjects()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  } finally {
    creating.value = false
  }
}

const logout = () => {
  auth.logout()
  router.push('/login')
}

const deleteProject = async () => {
  if (deleting.value) return
  if (!selectedProjects.value.length) return
  deleting.value = true
  try {
    const deletingIds = selectedProjects.value.map((p) => p.id)
    for (const id of deletingIds) {
      await api.delete(`/projects/${id}`, {
        data: {
          password: deleteForm.password,
          confirm_text: deleteForm.confirm_text
        }
      })
      if (String(auth.projectId) === String(id)) {
        auth.clearProject()
      }
    }
    ElMessage.success('工程已删除')
    deleteOpen.value = false
    selectedProjects.value = []
    await loadProjects()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  updateMobileDialog()
  window.addEventListener('close-all-dialogs', onCloseAllDialogs)
  window.addEventListener('resize', updateMobileDialog)
  loadProjects()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateMobileDialog)
  window.removeEventListener('close-all-dialogs', onCloseAllDialogs)
})
</script>

<style scoped>
.project-entry-wrap {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.project-entry-card {
  width: min(980px, 96vw);
}

.project-entry-title {
  text-align: center;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.08em;
  margin-bottom: 12px;
}

.project-toolbar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
}

.project-toolbar-title-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.08em;
  max-width: min(48vw, 460px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-toolbar-left,
.project-toolbar-right {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.project-toolbar-right {
  margin-left: auto;
}

:deep(.projects-table) {
  --el-table-border: 1px solid var(--table-line-color);
  --el-table-border-color: var(--table-line-color);
  --el-border-color-lighter: var(--table-line-color);
  --el-border-color-light: var(--table-line-color);
  border: 1px solid var(--table-line-color);
  --el-table-row-hover-bg-color: color-mix(in oklab, var(--accent) 12%, transparent);
}

:deep(.projects-table .el-table__cell),
:deep(.projects-table th.el-table__cell),
:deep(.projects-table td.el-table__cell) {
  border-color: var(--table-line-color) !important;
}

:deep(.projects-table .el-table__body tr td.el-table__cell),
:deep(.projects-table .el-table__header tr th.el-table__cell) {
  border-bottom: 0 !important;
  box-shadow: inset 0 -1px 0 var(--table-line-color) !important;
}

:deep(.projects-table .el-table__inner-wrapper::before),
:deep(.projects-table .el-table__inner-wrapper::after),
:deep(.projects-table .el-table__border-left-patch),
:deep(.projects-table::before),
:deep(.projects-table::after) {
  background-color: var(--table-line-color) !important;
}

:deep(.projects-table .el-table__row--striped td.el-table__cell) {
  background: var(--table-stripe-bg) !important;
}

@media (max-width: 900px) {
  .project-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .project-toolbar-title-center {
    position: static;
    left: auto;
    transform: none;
    width: 100%;
    max-width: 100%;
    order: -1;
    font-size: 16px;
    text-align: center;
    margin-bottom: 4px;
  }

  .project-toolbar-left,
  .project-toolbar-right {
    gap: 8px;
  }

  .project-entry-wrap {
    min-height: calc(100dvh - 24px);
    padding: 12px;
    align-items: center;
    justify-content: center;
    box-sizing: border-box;
  }

  .project-entry-card {
    width: 100%;
    max-height: calc(100dvh - 24px);
    box-sizing: border-box;
    margin: 0;
  }

  :deep(.project-entry-overlay) {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  :deep(.project-entry-overlay .project-entry-dialog.el-dialog) {
    margin: 0 !important;
    max-height: min(92vh, 680px);
    display: flex;
    flex-direction: column;
  }

  :deep(.project-entry-dialog .el-dialog__body) {
    flex: 1;
    max-height: none;
    overflow-y: auto;
  }
}
</style>
