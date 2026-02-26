import axios from 'axios'

const api = axios.create({
  baseURL: '/api'
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  const projectId = localStorage.getItem('projectId')
  if (projectId) {
    config.headers['X-Project-Id'] = projectId
  }
  return config
})

export default api
