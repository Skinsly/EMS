<template>
  <div class="login-wrap">
    <el-tooltip content="导入数据包" placement="top">
      <el-button
        circle
        class="login-settings-btn"
        aria-label="导入数据包"
        @click="openImportDialog = true"
      >
        <el-icon><Setting /></el-icon>
      </el-button>
    </el-tooltip>

    <div class="login-shell">
      <div class="login-card fade-up" style="animation-delay: 100ms">
        <div v-if="loginError" class="login-error-float">{{ loginError }}</div>
        <h2 class="login-title">工程管理</h2>
        <el-form class="login-form" @submit.prevent @keyup.enter="submit">
          <el-form-item>
            <el-input v-model="username" autocomplete="username" placeholder="请输入账号" />
          </el-form-item>
          <el-form-item>
            <el-input v-model="password" show-password autocomplete="current-password" placeholder="请输入密码" />
          </el-form-item>
          <el-button type="primary" class="login-btn" @click="submit">登录</el-button>
        </el-form>

        <el-dialog
          v-model="initDialogVisible"
          width="420px"
          :close-on-click-modal="false"
          :close-on-press-escape="false"
          :show-close="false"
          class="init-dialog"
          title="系统初始化"
        >
          <el-form @submit.prevent @keyup.enter="submitInit">
            <el-form-item>
              <el-input v-model="initUsername" autocomplete="username" placeholder="首次初始化账号" />
            </el-form-item>
            <el-form-item>
              <el-input v-model="initPassword" show-password autocomplete="new-password" placeholder="首次初始化密码（至少8位）" />
            </el-form-item>
          </el-form>
          <template #footer>
            <div class="init-dialog-footer">
              <el-button type="primary" class="login-btn init-submit-btn" @click="submitInit">确认初始化</el-button>
            </div>
          </template>
        </el-dialog>

        <el-dialog
          v-model="openImportDialog"
          width="420px"
          :close-on-click-modal="false"
          :close-on-press-escape="false"
          :show-close="false"
          modal-class="import-dialog-overlay"
          class="init-dialog import-dialog"
          align-center
        >
          <template #header>
            <div class="mac-dialog-header import-dialog-header">
              <div class="mac-dialog-controls">
                <el-tooltip content="关闭" placement="bottom">
                  <button class="mac-window-btn close" type="button" aria-label="关闭" @click="openImportDialog = false" />
                </el-tooltip>
              </div>
              <div class="mac-dialog-title">导入数据包</div>
            </div>
          </template>

          <p class="import-file-name">{{ importFileName || '未选择数据包' }}</p>
          <template #footer>
            <div class="import-dialog-footer">
              <el-upload
                class="import-uploader"
                :auto-upload="false"
                :show-file-list="false"
                :limit="1"
                accept=".db,.sqlite,.sqlite3"
                @change="onImportFileChange"
              >
                <el-tooltip content="选择数据包" placement="top">
                  <el-button circle class="icon-btn import-icon-btn" aria-label="选择数据包文件">
                    <el-icon><UploadFilled /></el-icon>
                  </el-button>
                </el-tooltip>
              </el-upload>
              <el-tooltip content="导入数据包" placement="top">
                <el-button circle class="icon-btn import-icon-btn" :loading="importing" aria-label="导入数据包" @click="importDataPackage">
                  <el-icon><Check /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </template>
        </el-dialog>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Setting, UploadFilled } from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../store'
import { createLoginActions } from './loginActions'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const initialized = ref(true)
const initUsername = ref('')
const initPassword = ref('')
const initDialogVisible = ref(false)
const openImportDialog = ref(false)
const importFileName = ref('')
const importFileRaw = ref(null)
const importing = ref(false)
const loginError = ref('')
let loginErrorTimer = null

const showLoginError = (message) => {
  loginError.value = message
  if (loginErrorTimer) {
    clearTimeout(loginErrorTimer)
    loginErrorTimer = null
  }
  loginErrorTimer = setTimeout(() => {
    loginError.value = ''
    loginErrorTimer = null
  }, 2600)
}

const actions = createLoginActions({
  auth,
  router,
  message: ElMessage,
  showLoginError
})

const submitInit = async () => {
  const initUser = initUsername.value.trim()
  const initPass = initPassword.value.trim()
  if (initUser.length < 3) {
    showLoginError('初始化账号至少 3 位')
    return
  }
  if (initPass.length < 8) {
    showLoginError('初始化密码至少 8 位')
    return
  }
  if (!/[A-Za-z]/.test(initPass) || !/\d/.test(initPass)) {
    showLoginError('初始化密码需包含字母和数字')
    return
  }

  try {
    await api.post('/bootstrap/init', {
      username: initUser,
      password: initPass
    })
    initialized.value = true
    initDialogVisible.value = false
    username.value = initUser
    password.value = initPass
    initPassword.value = ''
    ElMessage.success('初始化成功，请登录')
  } catch (e) {
    showLoginError(e.response?.data?.detail || '初始化失败')
  }
}

const submit = async () => {
  const result = await actions.submit({
    initialized,
    username,
    password,
    loginApi: (payload) => api.post('/auth/login', payload)
  })
  if (result?.status === 'needs-init') {
    initialized.value = false
    initDialogVisible.value = true
    result.onHandled?.()
  }
}

const onImportFileChange = (file) => {
  importFileRaw.value = file?.raw || null
  importFileName.value = file?.name || ''
}

const importDataPackage = async () => {
  if (!importFileRaw.value) {
    showLoginError('请先选择数据包文件')
    return
  }
  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', importFileRaw.value)
    await api.post('/bootstrap/import-package', formData)
    ElMessage.success('数据包导入成功，请登录')
    openImportDialog.value = false
    importFileName.value = ''
    importFileRaw.value = null
    await loadBootstrapStatus()
  } catch (e) {
    const detail = e.response?.data?.detail
    showLoginError(detail ? `导入失败：${detail}` : '导入失败，请检查数据包或稍后重试')
  } finally {
    importing.value = false
  }
}

const loadBootstrapStatus = async () => {
  try {
    const { data } = await api.get('/bootstrap/status')
    initialized.value = Boolean(data?.initialized)
    initDialogVisible.value = !initialized.value
  } catch {
    initialized.value = true
    initDialogVisible.value = false
  }
}

watch(openImportDialog, (visible) => {
  if (!visible) {
    importFileName.value = ''
    importFileRaw.value = null
  }
})

onBeforeUnmount(() => {
  if (loginErrorTimer) {
    clearTimeout(loginErrorTimer)
    loginErrorTimer = null
  }
})

loadBootstrapStatus()
</script>

<style scoped>
.login-card {
  position: relative;
  overflow: visible;
}

.login-wrap {
  position: relative;
}

.login-settings-btn {
  position: absolute;
  left: 16px;
  bottom: 16px;
  z-index: 5;
}

.import-file-name {
  margin: 4px 0 0;
  min-height: 38px;
  font-size: 13px;
  color: var(--muted);
  word-break: break-all;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
}

.import-uploader {
  display: flex;
  justify-content: flex-start;
}

.login-error-float {
  position: absolute;
  left: 50%;
  top: -42px;
  transform: translateX(-50%);
  max-width: min(86vw, 360px);
  padding: 7px 12px;
  border: 1px solid color-mix(in oklab, var(--el-color-danger) 58%, #ffffff 42%);
  border-radius: 10px;
  background: color-mix(in oklab, var(--el-color-danger) 18%, var(--surface-1));
  color: color-mix(in oklab, var(--el-color-danger) 86%, #10213a 14%);
  font-size: 13px;
  line-height: 1.35;
  text-align: center;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.2);
  z-index: 4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.init-dialog-footer {
  display: flex;
  justify-content: center;
}

.import-dialog-header {
  display: flex;
  justify-content: center;
  align-items: center;
}

.import-dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.import-icon-btn {
  margin: 0 !important;
}

.init-submit-btn {
  min-width: 132px;
}

:deep(.init-dialog .el-dialog__header) {
  text-align: center;
}

:deep(.init-dialog .el-dialog) {
  overflow: visible;
}

:deep(.init-dialog .el-dialog__body) {
  max-height: none !important;
  overflow: visible !important;
  padding-bottom: 8px;
}

:deep(.import-dialog) {
  width: min(420px, calc(100vw - 32px)) !important;
}

:deep(.init-dialog .el-dialog__title) {
  display: block;
  text-align: center;
}

:deep(.init-dialog .el-dialog__footer) {
  display: flex;
  justify-content: center;
}

:deep(.import-dialog .el-dialog__header) {
  padding-bottom: 8px;
}

:deep(.import-dialog .el-dialog__footer) {
  display: block;
}
</style>
