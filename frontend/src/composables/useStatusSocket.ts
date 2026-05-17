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

  function connect() {
    stopped = false
    const token = localStorage.getItem('access_token')
    if (!token) return
    if (socket && socket.readyState <= WebSocket.OPEN) return
    status.value = 'connecting'
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
