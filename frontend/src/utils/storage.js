const SESSION_KEYS = {
  username: 'username',
  token: 'token',
  projectId: 'projectId',
  projectName: 'projectName'
}

const PREFERENCE_KEYS = {
  theme: 'theme',
  sidebarCollapsed: 'sidebarCollapsed'
}

const read = (storage, key) => storage.getItem(key) || ''

export const storageKeys = {
  session: SESSION_KEYS,
  preferences: PREFERENCE_KEYS
}

export const readSession = (key) => read(sessionStorage, key)

export const writeSession = (key, value) => {
  sessionStorage.setItem(key, value)
}

export const removeSession = (key) => {
  sessionStorage.removeItem(key)
}

export const readPreference = (key) => read(localStorage, key)

export const writePreference = (key, value) => {
  localStorage.setItem(key, value)
}

export const removePreference = (key) => {
  localStorage.removeItem(key)
}
