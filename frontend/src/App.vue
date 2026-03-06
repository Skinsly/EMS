<template>
  <div class="app-shell">
    <el-container v-if="showMainLayout" class="layout-root">
      <el-aside
        :width="isMobileLayout ? '150px' : (isSidebarCollapsed ? '56px' : '184px')"
        class="app-aside"
        :class="{ 'mobile-mode': isMobileLayout, 'mobile-open': mobileMenuOpen }"
      >
          <div class="aside-brand" :class="{ collapsed: isSidebarCollapsed }">
            {{ isSidebarCollapsed ? 'EMS' : '工程管理系统' }}
          </div>
          <el-menu :default-active="$route.path" :collapse="isMobileLayout ? false : isSidebarCollapsed" :collapse-transition="false" router>
            <el-menu-item
              v-for="item in menuItems"
              :key="item.index"
              :index="item.index"
              :title="item.label"
              :aria-label="item.label"
            >
              <el-tooltip :content="item.label" placement="right" :disabled="!isMenuCollapsed">
                <div class="menu-item-inner">
                  <el-icon><component :is="item.icon" /></el-icon>
                  <div v-if="!isMenuCollapsed" class="menu-item-text">{{ item.label }}</div>
                </div>
              </el-tooltip>
            </el-menu-item>
          </el-menu>
          <div class="aside-actions" :class="{ collapsed: isSidebarCollapsed && !isMobileLayout }">
            <el-tooltip content="选择工程" placement="right">
              <el-button circle size="small" class="icon-btn" @click="goProjectEntry" aria-label="选择工程">
                <el-icon><OfficeBuilding /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="theme === 'dark' ? '切换浅色' : '切换深色'" placement="right">
              <el-button circle size="small" class="icon-btn" @click="toggleTheme" :aria-label="theme === 'dark' ? '切换浅色' : '切换深色'">
                <el-icon v-if="theme === 'dark'"><Sunny /></el-icon>
                <el-icon v-else><Moon /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip content="设置" placement="right">
              <el-button circle size="small" class="icon-btn" @click="openSettings = true" aria-label="设置">
                <el-icon><Setting /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip content="退出登录" placement="right">
              <el-button circle size="small" class="icon-btn danger" @click="logout" aria-label="退出登录">
                <el-icon><SwitchButton /></el-icon>
              </el-button>
            </el-tooltip>
          </div>
      </el-aside>

      <el-button
        v-if="!isMobileLayout"
        circle
        class="desktop-edge-toggle"
        :style="{ left: isSidebarCollapsed ? '56px' : '184px' }"
        @click="toggleSidebar"
        :aria-label="isSidebarCollapsed ? '展开菜单' : '隐藏菜单'"
      >
        <el-icon v-if="isSidebarCollapsed"><ArrowRightBold /></el-icon>
        <el-icon v-else><ArrowLeftBold /></el-icon>
      </el-button>

      <el-container class="content-wrap">
        <el-main class="app-main">
          <el-button
            v-if="isMobileLayout && !mobileMenuOpen"
            class="mobile-edge-toggle"
            @click="mobileMenuOpen = true"
            aria-label="打开菜单"
          >
            <el-icon><ArrowRightBold /></el-icon>
          </el-button>
          <router-view />
        </el-main>
      </el-container>
    </el-container>
    <div v-if="showMainLayout && isMobileLayout && mobileMenuOpen" class="aside-mask" @click="mobileMenuOpen = false"></div>
    <router-view v-if="!showMainLayout" />

    <el-dialog v-model="openSettings" width="420px" class="macos-dialog" :show-close="false">
      <template #header>
        <div class="mac-dialog-header">
          <div class="dialog-header-actions-left">
            <el-tooltip content="保存" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="保存" @click="changePwd">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="openSettings = false" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">设置</div>
        </div>
      </template>
      <el-form label-width="0" @keydown.enter.prevent="changePwd">
        <el-form-item>
          <el-input v-model="newUsername" placeholder="留空则不修改账号" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="oldPassword" show-password placeholder="请输入旧密码" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="newPassword" show-password placeholder="留空则不修改密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="login-btn" @click="exportDatabase">导出 app.db</el-button>
        </el-form-item>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeftBold,
  ArrowRightBold,
  Camera,
  Box,
  Calendar,
  Check,
  CollectionTag,
  Document,
  FolderOpened,
  Files,
  Moon,
  OfficeBuilding,
  Setting,
  Sort,
  Sunny,
  SwitchButton,
  Van
} from '@element-plus/icons-vue'
import api from './api'
import { downloadByApi } from './download'
import { useAuthStore } from './store'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const openSettings = ref(false)
const newUsername = ref('')
const oldPassword = ref('')
const newPassword = ref('')
const theme = ref('light')
const isSidebarCollapsed = ref(false)
const isMobileLayout = ref(false)
const mobileMenuOpen = ref(false)
const lastDraftPendingToastTotal = ref(-1)
const menuItems = [
  { index: '/construction-logs', label: '施工日志', icon: Document },
  { index: '/file-manage', label: '文件管理', icon: FolderOpened },
  { index: '/machine-ledger', label: '机械台账', icon: Van },
  { index: '/site-photos', label: '现场照片', icon: Camera },
  { index: '/materials', label: '材料管理', icon: Box },
  { index: '/stock-manage', label: '出入管理', icon: Sort },
  { index: '/stock-records', label: '出入记录', icon: Files },
  { index: '/inventory', label: '库存台账', icon: CollectionTag },
  { index: '/progress-plan', label: '进度计划', icon: Calendar }
]
const isMenuCollapsed = computed(() => !isMobileLayout.value && isSidebarCollapsed.value)

const showMainLayout = computed(() => route.path !== '/login' && route.path !== '/projects')

const updateMobileLayout = () => {
  isMobileLayout.value = window.matchMedia('(max-width: 900px)').matches
  if (!isMobileLayout.value) {
    mobileMenuOpen.value = false
  }
}

const applyTheme = (mode) => {
  document.documentElement.setAttribute('data-theme', mode)
}

const toggleTheme = () => {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
}

const toggleSidebar = () => {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  localStorage.setItem('sidebarCollapsed', isSidebarCollapsed.value ? '1' : '0')
  window.dispatchEvent(
    new CustomEvent('sidebar-collapse-changed', {
      detail: { collapsed: isSidebarCollapsed.value }
    })
  )
}

const goProjectEntry = () => {
  router.push('/projects')
}

const onCloseAllDialogs = () => {
  openSettings.value = false
}

const loadDraftPending = async () => {
  if (!showMainLayout.value) return
  try {
    const { data } = await api.get('/stock-drafts/pending/count')
    const total = Number(data?.total || 0)
    if (total > 0 && total !== lastDraftPendingToastTotal.value) {
      ElMessage.warning(`你有 ${total} 条待入账草稿`)
    }
    lastDraftPendingToastTotal.value = total
  } catch {
    // ignore draft reminder failures
  }
}

onMounted(() => {
  updateMobileLayout()
  window.addEventListener('resize', updateMobileLayout)

  const saved = localStorage.getItem('theme')
  if (saved === 'dark' || saved === 'light') {
    theme.value = saved
  } else {
    theme.value = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  applyTheme(theme.value)

  const savedSidebar = localStorage.getItem('sidebarCollapsed')
  if (savedSidebar === '1') {
    isSidebarCollapsed.value = true
  }
  window.dispatchEvent(
    new CustomEvent('sidebar-collapse-changed', {
      detail: { collapsed: isSidebarCollapsed.value }
    })
  )

  loadDraftPending()
  window.addEventListener('close-all-dialogs', onCloseAllDialogs)

})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateMobileLayout)
  window.removeEventListener('close-all-dialogs', onCloseAllDialogs)
})

watch(theme, (value) => {
  localStorage.setItem('theme', value)
  applyTheme(value)
})

watch(
  () => route.path,
  () => {
    mobileMenuOpen.value = false
    loadDraftPending()
  }
)

const logout = () => {
  auth.logout()
  router.push('/login')
}

const changePwd = async () => {
  const usernameValue = newUsername.value.trim()
  const passwordValue = newPassword.value.trim()
  if (!usernameValue && !passwordValue) {
    ElMessage.error('请至少填写新账号或新密码')
    return
  }
  try {
    const { data } = await api.post('/auth/change-password', {
      old_password: oldPassword.value,
      new_username: usernameValue,
      new_password: passwordValue
    })
    if (data?.username_changed && data?.username) {
      auth.setUsername(data.username)
    }
    ElMessage.success('账号和密码信息已更新')
    openSettings.value = false
    newUsername.value = ''
    oldPassword.value = ''
    newPassword.value = ''
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '修改失败')
  }
}

const exportDatabase = async () => {
  try {
    await downloadByApi('/export/database', 'app.db')
    ElMessage.success('数据库导出成功')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '数据库导出失败')
  }
}

</script>
