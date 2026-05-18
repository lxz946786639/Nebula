import { ref } from 'vue'

interface StatusSocketOptions {
  topics: string[]
  intervalMs?: number
}

export function useStatusSocket(onMessage: (payload: Record<string, unknown>) => void, options: StatusSocketOptions) {
  const connected = ref(false)
  const status = ref<'idle' | 'connecting' | 'connected' | 'reconnecting' | 'disconnected'>('idle')
  let socket: WebSocket | null = null
  let reconnectTimer: number | undefined
  let stopped = false
  let refreshPromise: Promise<string | null> | null = null

  function clearAuthStorage() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('username')
  }

  function decodeJwtPayload(token: string): { exp?: number } | null {
    const payload = token.split('.')[1]
    if (!payload) return null
    try {
      const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
      const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
      return JSON.parse(window.atob(padded)) as { exp?: number }
    } catch {
      return null
    }
  }

  function tokenExpiresSoon(token: string) {
    const payload = decodeJwtPayload(token)
    if (!payload?.exp) return false
    return payload.exp * 1000 <= Date.now() + 30_000
  }

  async function refreshAccessToken() {
    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) return null
    if (!refreshPromise) {
      refreshPromise = fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
        .then(async (response) => {
          if (!response.ok) return null
          const data = (await response.json()) as { access_token?: string; refresh_token?: string }
          if (!data.access_token || !data.refresh_token) return null
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          return data.access_token
        })
        .catch(() => null)
        .finally(() => {
          refreshPromise = null
        })
    }
    return refreshPromise
  }

  async function currentAccessToken() {
    const token = localStorage.getItem('access_token')
    if (token && !tokenExpiresSoon(token)) return token
    const refreshed = await refreshAccessToken()
    if (refreshed) return refreshed
    if (token && tokenExpiresSoon(token)) clearAuthStorage()
    return null
  }

  function stop() {
    stopped = true
    connected.value = false
    status.value = 'disconnected'
    if (reconnectTimer) window.clearTimeout(reconnectTimer)
    reconnectTimer = undefined
    if (socket) socket.close()
    socket = null
  }

  function scheduleReconnect() {
    if (stopped || reconnectTimer) return
    status.value = 'reconnecting'
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = undefined
      connect()
    }, 3000)
  }

  async function connect() {
    stopped = false
    if (socket && socket.readyState <= WebSocket.OPEN) return
    status.value = 'connecting'
    const token = await currentAccessToken()
    if (!token) {
      status.value = 'disconnected'
      return
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const params = new URLSearchParams({
      token,
      topics: options.topics.join(','),
      interval_ms: String(options.intervalMs || 10000),
    })
    socket = new WebSocket(`${protocol}//${window.location.host}/api/ws/status?${params.toString()}`)
    socket.onopen = () => {
      connected.value = true
      status.value = 'connected'
    }
    socket.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data))
      } catch {
        // Ignore malformed messages; the next status frame will replace it.
      }
    }
    socket.onclose = () => {
      connected.value = false
      status.value = stopped ? 'disconnected' : 'reconnecting'
      socket = null
      scheduleReconnect()
    }
    socket.onerror = () => {
      connected.value = false
      status.value = 'reconnecting'
      socket?.close()
    }
  }

  return { connected, status, connect, stop }
}
