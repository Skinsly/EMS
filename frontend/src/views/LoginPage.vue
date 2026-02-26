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
          :show-close="false"
          class="init-dialog"
          title="导入数据包"
        >
          <el-upload
            class="import-uploader"
            :auto-upload="false"
            :show-file-list="false"
            :limit="1"
            accept=".db,.sqlite,.sqlite3"
            @change="onImportFileChange"
          >
            <button type="button" class="import-picker-btn" aria-label="选择数据包文件">
              <el-icon><UploadFilled /></el-icon>
              <span>选择数据包</span>
            </button>
          </el-upload>
          <p class="import-file-name">{{ importFileName || '未选择文件' }}</p>
          <template #footer>
            <div class="init-dialog-footer">
              <el-button type="primary" class="login-btn init-submit-btn" :loading="importing" @click="importDataPackage">导入数据包</el-button>
            </div>
          </template>
        </el-dialog>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Setting, UploadFilled } from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../store'

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
  try {
    if (!initialized.value) {
      initDialogVisible.value = true
      showLoginError('系统未初始化，请先设置账号密码')
      return
    }
    const { data } = await api.post('/auth/login', {
      username: username.value,
      password: password.value
    })
    auth.setAuth(username.value, data.access_token)
    auth.clearProject()
    ElMessage.success('登录成功')
    router.push('/projects')
  } catch (e) {
    if (e.response?.data?.detail === '系统未初始化，请先创建管理员账号') {
      initialized.value = false
      initDialogVisible.value = true
      showLoginError('系统未初始化，请先设置账号密码')
      return
    }
    showLoginError(e.response?.data?.detail || '登录失败')
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
  margin: 12px 0 0;
  font-size: 13px;
  color: var(--muted);
  word-break: break-all;
  text-align: center;
}

.import-uploader {
  display: flex;
  justify-content: center;
}

.import-picker-btn {
  min-width: 178px;
  height: 40px;
  border: 1px solid color-mix(in oklab, var(--accent) 34%, var(--divider-strong) 66%);
  border-radius: 10px;
  background: linear-gradient(145deg, color-mix(in oklab, var(--surface-1) 78%, #ffffff 22%), color-mix(in oklab, var(--accent) 10%, var(--surface-2) 90%));
  color: var(--text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease);
}

.import-picker-btn:hover {
  border-color: color-mix(in oklab, var(--accent) 48%, var(--divider-strong) 52%);
  background: linear-gradient(145deg, color-mix(in oklab, var(--surface-1) 64%, #ffffff 36%), color-mix(in oklab, var(--accent) 16%, var(--surface-2) 84%));
}

.import-picker-btn:active {
  transform: translateY(1px);
}

.import-picker-btn .el-icon {
  font-size: 16px;
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

.init-submit-btn {
  min-width: 132px;
}

:deep(.init-dialog .el-dialog__header) {
  text-align: center;
}

:deep(.init-dialog .el-dialog__title) {
  display: block;
  text-align: center;
}

:deep(.init-dialog .el-dialog__footer) {
  display: flex;
  justify-content: center;
}
</style>
