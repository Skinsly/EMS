import { defineStore } from 'pinia'
import { readSession, removeSession, storageKeys, writeSession } from './utils/storage'

export const getSessionToken = () => readSession(storageKeys.session.token)
export const getSessionUsername = () => readSession(storageKeys.session.username)
export const getSessionProjectId = () => readSession(storageKeys.session.projectId)
export const getSessionProjectName = () => readSession(storageKeys.session.projectName)
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
      writeSession(storageKeys.session.username, username)
      writeSession(storageKeys.session.token, token)
    },
    setUsername(username) {
      this.username = username
      writeSession(storageKeys.session.username, username)
    },
    setProject(project) {
      this.projectId = String(project.id)
      this.projectName = project.name
      writeSession(storageKeys.session.projectId, String(project.id))
      writeSession(storageKeys.session.projectName, project.name)
    },
    clearProject() {
      this.projectId = ''
      this.projectName = ''
      removeSession(storageKeys.session.projectId)
      removeSession(storageKeys.session.projectName)
    },
    logout() {
      this.username = ''
      this.token = ''
      removeSession(storageKeys.session.username)
      removeSession(storageKeys.session.token)
      this.clearProject()
    }
  }
})
