import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

const http = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

let refreshPromise: Promise<string | null> | null = null
let sessionExpiredNotified = false

function isAuthRequest(config?: InternalAxiosRequestConfig) {
  const url = config?.url || ''
  return url.includes('/auth/login') || url.includes('/auth/refresh') || url.includes('/auth/logout')
}

function isLoginRequest(config?: InternalAxiosRequestConfig) {
  return (config?.url || '').includes('/auth/login')
}

function errorMessage(error: AxiosError) {
  const data = error.response?.data as { detail?: unknown } | undefined
  const message = data?.detail || error.message || '请求失败'
  if (message === 'Invalid username or password') return '用户名或密码错误'
  if (message === 'Access token expired' || message === 'Refresh token expired') return '登录已过期，请重新登录'
  if (message === 'Invalid bearer token' || message === 'Invalid refresh token') return '登录状态无效，请重新登录'
  return message
}

function clearAuthStorage() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('username')
}

function redirectToLogin() {
  if (location.pathname === '/login') return
  const currentPath = `${location.pathname}${location.search}`
  const redirect = currentPath && currentPath !== '/login' ? `?redirect=${encodeURIComponent(currentPath)}` : ''
  location.href = `/login${redirect}`
}

function handleSessionExpired() {
  clearAuthStorage()
  if (!sessionExpiredNotified) {
    sessionExpiredNotified = true
    ElMessage.warning('登录已过期，请重新登录')
  }
  redirectToLogin()
}

async function refreshAccessToken() {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) return null
  if (!refreshPromise) {
    refreshPromise = axios
      .post('/api/auth/refresh', { refresh_token: refreshToken }, { timeout: 60000 })
      .then((response) => {
        const accessToken = response.data?.access_token as string | undefined
        const nextRefreshToken = response.data?.refresh_token as string | undefined
        if (!accessToken || !nextRefreshToken) return null
        localStorage.setItem('access_token', accessToken)
        localStorage.setItem('refresh_token', nextRefreshToken)
        return accessToken
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const status = error.response?.status
    const config = error.config as RetryableRequestConfig | undefined

    if (status === 401 && !isAuthRequest(config)) {
      if (config && !config._retry) {
        config._retry = true
        const accessToken = await refreshAccessToken()
        if (accessToken) {
          config.headers.Authorization = `Bearer ${accessToken}`
          return http(config)
        }
      }
      handleSessionExpired()
      return Promise.reject(error)
    }

    if (status === 401 && !isLoginRequest(config)) {
      handleSessionExpired()
      return Promise.reject(error)
    }

    ElMessage.error(String(errorMessage(error)))
    return Promise.reject(error)
  },
)

export default http
