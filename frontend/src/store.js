import { defineStore } from 'pinia'

const readSession = (key) => sessionStorage.getItem(key) || ''

export const setSessionValue = (key, value) => {
  sessionStorage.setItem(key, value)
}

export const removeSessionValue = (key) => {
  sessionStorage.removeItem(key)
}

export const getSessionToken = () => readSession('token')
export const getSessionUsername = () => readSession('username')
export const getSessionProjectId = () => readSession('projectId')
export const getSessionProjectName = () => readSession('projectName')
export const getSessionValue = readSession

export const useAuthStore = defineStore('auth', {
  state: () => ({
    username: getSessionUsername(),
    token: getSessionToken(),
    projectId: getSessionProjectId(),
    projectName: getSessionProjectName()
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token),
    hasProject: (state) => Boolean(state.projectId)
  },
  actions: {
    setAuth(username, token) {
      this.username = username
      this.token = token
      setSessionValue('username', username)
      setSessionValue('token', token)
    },
    setUsername(username) {
      this.username = username
      setSessionValue('username', username)
    },
    setProject(project) {
      this.projectId = String(project.id)
      this.projectName = project.name
      setSessionValue('projectId', String(project.id))
      setSessionValue('projectName', project.name)
    },
    clearProject() {
      this.projectId = ''
      this.projectName = ''
      removeSessionValue('projectId')
      removeSessionValue('projectName')
    },
    logout() {
      this.username = ''
      this.token = ''
      removeSessionValue('username')
      removeSessionValue('token')
      localStorage.removeItem('username')
      localStorage.removeItem('token')
      localStorage.removeItem('projectId')
      localStorage.removeItem('projectName')
      this.clearProject()
    }
  }
})
