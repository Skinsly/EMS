import { createRouter, createWebHashHistory } from 'vue-router'
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

const routes = [
  { path: '/login', component: LoginPage },
  { path: '/', redirect: '/projects' },
  { path: '/projects', component: ProjectsPage },
  { path: '/materials', component: MaterialsPage },
  { path: '/construction-logs', component: ConstructionLogsPage },
  { path: '/progress-plan', component: ProgressPlanPage },
  { path: '/stock-manage', component: StockManagePage },
  { path: '/stock-records', component: StockRecordsPage },
  { path: '/stock-in', redirect: '/stock-manage?mode=in' },
  { path: '/stock-out', redirect: '/stock-manage?mode=out' },
  { path: '/inventory', component: InventoryPage },
  { path: '/machine-ledger', component: MachineLedgerPage },
  { path: '/site-photos', component: SitePhotosPage }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  const projectId = localStorage.getItem('projectId')
  if (to.path !== '/login' && !token) {
    return '/login'
  }
  if (to.path === '/login' && token) {
    return '/projects'
  }
  if (token && to.path !== '/projects' && !projectId) {
    return '/projects'
  }
  return true
})

export default router
