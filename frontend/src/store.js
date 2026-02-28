import { defineStore } from 'pinia'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    username: sessionStorage.getItem('username') || '',
    projectId: sessionStorage.getItem('projectId') || '',
    projectName: sessionStorage.getItem('projectName') || ''
  }),
  actions: {
    setAuth(username, token) {
      this.username = username
      sessionStorage.setItem('username', username)
      sessionStorage.setItem('token', token)
    },
    setUsername(username) {
      this.username = username
      sessionStorage.setItem('username', username)
    },
    setProject(project) {
      this.projectId = String(project.id)
      this.projectName = project.name
      sessionStorage.setItem('projectId', String(project.id))
      sessionStorage.setItem('projectName', project.name)
    },
    clearProject() {
      this.projectId = ''
      this.projectName = ''
      sessionStorage.removeItem('projectId')
      sessionStorage.removeItem('projectName')
    },
    logout() {
      this.username = ''
      sessionStorage.removeItem('username')
      sessionStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('token')
      localStorage.removeItem('projectId')
      localStorage.removeItem('projectName')
      this.clearProject()
    }
  }
})
