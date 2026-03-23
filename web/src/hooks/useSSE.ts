import { useEffect } from 'react'

interface SSEMessage {
  text: string
  agent_name: string | null
  timestamp: string
  event_id: string
}

export function useSSE(
  conversationId: string | null,
  onMessage: (data: SSEMessage) => void,
) {
  useEffect(() => {
    if (!conversationId) return

    const source = new EventSource(`/conversations/${conversationId}/stream`)
    source.addEventListener('message', (e) => {
      onMessage(JSON.parse(e.data))
    })

    return () => source.close()
  }, [conversationId, onMessage])
}
