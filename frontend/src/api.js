import axios from 'axios'
import { getSessionProjectId, getSessionToken } from './store'

export const applyAuthHeaders = (config) => {
  const nextConfig = config
  if (!nextConfig.headers) {
    nextConfig.headers = {}
  }
  const token = getSessionToken()
  if (token) {
    nextConfig.headers.Authorization = `Bearer ${token}`
  }

  const projectId = getSessionProjectId()
  if (projectId) {
    nextConfig.headers['X-Project-Id'] = projectId
  }
  return nextConfig
}

const api = axios.create({
  baseURL: '/api'
})

api.interceptors.request.use(applyAuthHeaders)

export default api
