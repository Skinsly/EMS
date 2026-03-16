import { createRouter, createWebHashHistory } from 'vue-router'
import { getSessionProjectId, getSessionToken } from './store'
const LoginPage = () => import('./views/LoginPage.vue')
const ProjectsPage = () => import('./views/ProjectsPage.vue')
const MaterialsPage = () => import('./views/MaterialsPage.vue')
const ConstructionLogsPage = () => import('./views/ConstructionLogsPage.vue')
const ProgressPlanPage = () => import('./views/ProgressPlanPage.vue')
const StockManagePage = () => import('./views/StockManagePage.vue')
const StockRecordsPage = () => import('./views/StockRecordsPage.vue')
const InventoryPage = () => import('./views/InventoryPage.vue')
const MachineLedgerPage = () => import('./views/MachineLedgerPage.vue')
const SitePhotosPage = () => import('./views/SitePhotosPage.vue')
const FileManagePage = () => import('./views/FileManagePage.vue')

const routes = [
  { path: '/login', component: LoginPage, meta: { public: true, redirectIfAuthed: '/projects' } },
  { path: '/', redirect: '/projects' },
  { path: '/projects', component: ProjectsPage, meta: { requiresAuth: true } },
  { path: '/materials', component: MaterialsPage, meta: { requiresAuth: true, requiresProject: true } },
  { path: '/construction-logs', component: ConstructionLogsPage, meta: { requiresAuth: true, requiresProject: true } },
  { path: '/progress-plan', component: ProgressPlanPage, meta: { requiresAuth: true, requiresProject: true } },
  { path: '/stock-manage', component: StockManagePage, meta: { requiresAuth: true, requiresProject: true } },
  { path: '/stock-records', component: StockRecordsPage, meta: { requiresAuth: true, requiresProject: true } },
  { path: '/stock-in', redirect: '/stock-manage?mode=in' },
  { path: '/stock-out', redirect: '/stock-manage?mode=out' },
  { path: '/inventory', component: InventoryPage, meta: { requiresAuth: true, requiresProject: true } },
  { path: '/machine-ledger', component: MachineLedgerPage, meta: { requiresAuth: true, requiresProject: true } },
  { path: '/site-photos', component: SitePhotosPage, meta: { requiresAuth: true, requiresProject: true } },
  { path: '/file-manage', component: FileManagePage, meta: { requiresAuth: true, requiresProject: true } }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export const resolveRouteGuard = (to) => {
  const token = getSessionToken()
  const projectId = getSessionProjectId()
  if (to.meta?.redirectIfAuthed && token) {
    return to.meta.redirectIfAuthed
  }
  if (to.meta?.requiresAuth && !token) {
    return '/login'
  }
  if (token && to.meta?.requiresProject && !projectId) {
    return '/projects'
  }
  return true
}

router.beforeEach(resolveRouteGuard)

export default router
