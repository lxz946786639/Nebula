import { defineStore } from 'pinia'

import http from '@/api/http'

interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    accessToken: localStorage.getItem('access_token') || '',
    refreshToken: localStorage.getItem('refresh_token') || '',
    username: localStorage.getItem('username') || '',
  }),
  actions: {
    async login(username: string, password: string) {
      const { data } = await http.post<LoginResponse>('/auth/login', { username, password })
      this.accessToken = data.access_token
      this.refreshToken = data.refresh_token
      this.username = username
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      localStorage.setItem('username', username)
    },
    async logout(remote = true) {
      try {
        if (remote && (this.accessToken || localStorage.getItem('access_token'))) {
          await http.post('/auth/logout')
        }
      } catch {
        // Local logout should still succeed if the server session is already expired.
      } finally {
        this.accessToken = ''
        this.refreshToken = ''
        this.username = ''
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('username')
      }
    },
  },
})
