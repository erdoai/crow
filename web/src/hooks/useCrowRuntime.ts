import { useState, useCallback, useEffect } from 'react'
import {
  useExternalStoreRuntime,
  type ThreadMessageLike,
  type AppendMessage,
} from '@assistant-ui/react'
import { fetchJSON, type Message } from '../api'

/**
 * Bridges our backend (POST /messages + SSE) to assistant-ui's ExternalStoreRuntime.
 */
export function useCrowRuntime(
  conversationId: string | null,
  threadId: string | null,
  onConversationCreated?: () => void,
) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isRunning, setIsRunning] = useState(false)

  // Load messages when conversation changes
  useEffect(() => {
    if (!conversationId) {
      setMessages([])
      return
    }
    fetchJSON<Message[]>(`/conversations/${conversationId}/messages`).then(setMessages)
  }, [conversationId])

  // SSE subscription for real-time responses
  useEffect(() => {
    if (!conversationId) return

    const source = new EventSource(`/conversations/${conversationId}/stream`)
    source.addEventListener('message', (e) => {
      const data = JSON.parse(e.data) as {
        text: string
        agent_name: string | null
        timestamp: string
        event_id: string
      }
      setMessages((prev) => [
        ...prev,
        {
          id: data.event_id,
          role: 'assistant',
          content: data.text,
          agent_name: data.agent_name,
        },
      ])
      setIsRunning(false)
    })

    return () => source.close()
  }, [conversationId])

  const convertMessage = useCallback(
    (msg: Message): ThreadMessageLike => ({
      id: msg.id,
      role: msg.role,
      content: [{ type: 'text', text: msg.content }],
      ...(msg.role === 'assistant' && msg.agent_name
        ? { metadata: { custom: { agentName: msg.agent_name } } }
        : {}),
    }),
    [],
  )

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const textPart = message.content.find((p) => p.type === 'text')
      if (!textPart || textPart.type !== 'text') return

      const text = textPart.text
      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
        agent_name: null,
      }

      setMessages((prev) => [...prev, userMsg])
      setIsRunning(true)

      await fetchJSON('/messages', {
        method: 'POST',
        body: JSON.stringify({
          text,
          thread_id: threadId || 'default',
        }),
      })

      onConversationCreated?.()
    },
    [threadId, onConversationCreated],
  )

  const runtime = useExternalStoreRuntime({
    messages,
    isRunning,
    convertMessage,
    onNew,
  })

  return { runtime, messages, setMessages }
}
