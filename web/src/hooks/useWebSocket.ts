import { useCallback, useEffect, useRef } from 'react'
import { fetchJSON } from '../api'

interface UseWebSocketOptions {
  /** Called for every event received (live or replayed) */
  onEvent: (event: { type: string; data: Record<string, unknown>; seq: number }) => void
  /** Whether the connection is enabled */
  enabled: boolean
}

/**
 * Auto-reconnecting WebSocket with catch-up replay.
 *
 * Flow:
 * 1. POST /ws/token to get an ephemeral token (authed via cookie)
 * 2. Connect to ws://.../ws?token=...&last_seq=N
 * 3. Server replays missed events, then streams live
 * 4. On disconnect, reconnect with exponential backoff
 */
export function useWebSocket({ onEvent, enabled }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const lastSeqRef = useRef(0)
  const reconnectDelayRef = useRef(1000)
  const mountedRef = useRef(true)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const connect = useCallback(async () => {
    if (!mountedRef.current) return

    try {
      // Get ephemeral token
      const { token } = await fetchJSON<{ token: string }>('/ws/token', {
        method: 'POST',
      })

      if (!mountedRef.current) return

      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${proto}//${location.host}/ws?token=${token}&last_seq=${lastSeqRef.current}`
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        reconnectDelayRef.current = 1000 // reset backoff
      }

      ws.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data)
          if (event.type === 'ping' || event.type === 'keepalive') return
          if (event.seq && event.seq > lastSeqRef.current) {
            lastSeqRef.current = event.seq
          }
          onEventRef.current(event)
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        wsRef.current = null
        if (!mountedRef.current) return
        // Reconnect with exponential backoff + jitter
        const delay = reconnectDelayRef.current * (1 + Math.random() * 0.3)
        reconnectDelayRef.current = Math.min(
          reconnectDelayRef.current * 2,
          30_000,
        )
        setTimeout(() => connect(), delay)
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch {
      // Token fetch failed — retry with backoff
      if (!mountedRef.current) return
      const delay = reconnectDelayRef.current * (1 + Math.random() * 0.3)
      reconnectDelayRef.current = Math.min(
        reconnectDelayRef.current * 2,
        30_000,
      )
      setTimeout(() => connect(), delay)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    if (enabled) {
      connect()
    }
    return () => {
      mountedRef.current = false
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [enabled, connect])
}
