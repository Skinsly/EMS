import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

export const useAppShell = ({ route, api, notify, readPreference, storageKeys, writePreference }) => {
  const theme = ref('light')
  const isSidebarCollapsed = ref(false)
  const isMobileLayout = ref(false)
  const mobileMenuOpen = ref(false)
  const lastDraftPendingToastTotal = ref(-1)

  const showMainLayout = computed(() => route.path !== '/login' && route.path !== '/projects')
  const isMenuCollapsed = computed(() => !isMobileLayout.value && isSidebarCollapsed.value)

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

  const emitSidebarChange = () => {
    window.dispatchEvent(
      new CustomEvent('sidebar-collapse-changed', {
        detail: { collapsed: isSidebarCollapsed.value }
      })
    )
  }

  const toggleSidebar = () => {
    isSidebarCollapsed.value = !isSidebarCollapsed.value
    writePreference(storageKeys.preferences.sidebarCollapsed, isSidebarCollapsed.value ? '1' : '0')
    emitSidebarChange()
  }

  const loadDraftPending = async () => {
    if (!showMainLayout.value) return
    try {
      const { data } = await api.get('/stock-drafts/pending/count')
      const total = Number(data?.total || 0)
      if (total > 0 && total !== lastDraftPendingToastTotal.value) {
        notify.warning(`你有 ${total} 条待入账草稿`)
      }
      lastDraftPendingToastTotal.value = total
    } catch {
      // ignore draft reminder failures
    }
  }

  onMounted(() => {
    updateMobileLayout()
    window.addEventListener('resize', updateMobileLayout)

    const savedTheme = readPreference(storageKeys.preferences.theme)
    if (savedTheme === 'dark' || savedTheme === 'light') {
      theme.value = savedTheme
    } else {
      theme.value = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    applyTheme(theme.value)

    if (readPreference(storageKeys.preferences.sidebarCollapsed) === '1') {
      isSidebarCollapsed.value = true
    }
    emitSidebarChange()
    loadDraftPending()
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', updateMobileLayout)
  })

  watch(theme, (value) => {
    writePreference(storageKeys.preferences.theme, value)
    applyTheme(value)
  })

  watch(
    () => route.path,
    () => {
      mobileMenuOpen.value = false
      loadDraftPending()
    }
  )

  return {
    theme,
    isSidebarCollapsed,
    isMobileLayout,
    mobileMenuOpen,
    showMainLayout,
    isMenuCollapsed,
    toggleTheme,
    toggleSidebar,
    loadDraftPending
  }
}
