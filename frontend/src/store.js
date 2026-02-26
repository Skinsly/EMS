import { defineStore } from 'pinia'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    username: localStorage.getItem('username') || '',
    projectId: localStorage.getItem('projectId') || '',
    projectName: localStorage.getItem('projectName') || ''
  }),
  actions: {
    setAuth(username, token) {
      this.username = username
      localStorage.setItem('username', username)
      localStorage.setItem('token', token)
    },
    setUsername(username) {
      this.username = username
      localStorage.setItem('username', username)
    },
    setProject(project) {
      this.projectId = String(project.id)
      this.projectName = project.name
      localStorage.setItem('projectId', String(project.id))
      localStorage.setItem('projectName', project.name)
    },
    clearProject() {
      this.projectId = ''
      this.projectName = ''
      localStorage.removeItem('projectId')
      localStorage.removeItem('projectName')
    },
    logout() {
      this.username = ''
      localStorage.removeItem('username')
      localStorage.removeItem('token')
      this.clearProject()
    }
  }
})
