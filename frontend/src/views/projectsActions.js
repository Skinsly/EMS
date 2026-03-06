export const createProjectsActions = ({ auth, router, message }) => ({
  enterProject(project) {
    if (!project) return
    auth.setProject(project)
    message.success(`已切换到工程: ${project.name}`)
    router.push('/construction-logs')
  },
  clearDeletedProjects(deletingIds) {
    const ids = Array.isArray(deletingIds) ? deletingIds.map((id) => String(id)) : []
    if (!ids.length) return
    if (ids.includes(String(auth.projectId || ''))) {
      auth.clearProject()
    }
  },
  logout() {
    auth.logout()
    router.push('/login')
  }
})
