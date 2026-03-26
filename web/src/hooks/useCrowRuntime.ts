import { useState, useCallback, useEffect } from 'react'
import {
  useExternalStoreRuntime,
  type ThreadMessageLike,
  type AppendMessage,
} from '@assistant-ui/react'
import { fetchJSON, type Message } from '../api'

export interface CurrentActivity {
  type: 'tool' | 'progress' | 'thinking'
  text: string
  agentName?: string
}

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
  const [currentActivity, setCurrentActivity] = useState<CurrentActivity | null>(null)
  const [backgroundMode, setBackgroundMode] = useState(false)

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
    let streamingId: string | null = null
    type Part = { type: string; text?: string; name?: string; input?: Record<string, unknown>; result?: string }
    let streamedParts: Part[] = []

    source.addEventListener('chunk', (e) => {
      const data = JSON.parse(e.data) as {
        type: string
        text: string | null
        tool_name: string | null
        agent_name: string | null
        job_id: string
      }
      if (!streamingId) {
        streamingId = `streaming-${data.job_id}`
      }

      if (data.type === 'tool_call') {
        streamedParts.push({ type: 'tool_call', name: data.tool_name! })
        setCurrentActivity({ type: 'tool', text: data.tool_name!, agentName: data.agent_name ?? undefined })
      } else if (data.type === 'tool_result') {
        // Find the matching tool_call and add result
        for (let i = streamedParts.length - 1; i >= 0; i--) {
          if (streamedParts[i].type === 'tool_call' && streamedParts[i].name === data.tool_name) {
            // Insert result right after the tool_call
            streamedParts.splice(i + 1, 0, { type: 'tool_result', name: data.tool_name!, result: data.text ?? '' })
            break
          }
        }
      } else if (data.text) {
        // Append to last text part or create new one
        const last = streamedParts[streamedParts.length - 1]
        if (last?.type === 'text') {
          last.text = (last.text ?? '') + data.text
        } else {
          streamedParts.push({ type: 'text', text: data.text })
        }
        setCurrentActivity({ type: 'thinking', text: 'generating response...', agentName: data.agent_name ?? undefined })
      }

      const id = streamingId
      const content = JSON.stringify(streamedParts)
      const agentName = data.agent_name
      setMessages((prev) => {
        const existing = prev.findIndex((m) => m.id === id)
        const msg: Message = { id, role: 'assistant', content, agent_name: agentName }
        if (existing >= 0) {
          const next = [...prev]
          next[existing] = msg
          return next
        }
        return [...prev, msg]
      })
    })

    source.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data) as {
        status: string
        agent_name: string | null
        job_id: string
      }
      // Show progress as a streaming assistant message
      const id = streamingId || `streaming-${data.job_id}`
      if (!streamingId) streamingId = id

      setCurrentActivity({ type: 'progress', text: data.status, agentName: data.agent_name ?? undefined })

      // Add or update a progress text part
      const progressText = `*${data.agent_name || 'agent'}:* ${data.status}`
      const last = streamedParts[streamedParts.length - 1]
      if (last?.type === 'progress') {
        last.text = progressText
      } else {
        streamedParts.push({ type: 'progress', text: progressText })
      }

      const content = JSON.stringify(streamedParts)
      const agentName = data.agent_name
      setMessages((prev) => {
        const existing = prev.findIndex((m) => m.id === id)
        const msg: Message = { id, role: 'assistant', content, agent_name: agentName }
        if (existing >= 0) {
          const next = [...prev]
          next[existing] = msg
          return next
        }
        return [...prev, msg]
      })
    })

    source.addEventListener('message', (e) => {
      const data = JSON.parse(e.data) as {
        text: string
        agent_name: string | null
        timestamp: string
        event_id: string
      }
      // Replace streaming message with final version
      setMessages((prev) => {
        const finalMsg: Message = {
          id: data.event_id,
          role: 'assistant',
          content: data.text,
          agent_name: data.agent_name,
        }
        if (streamingId) {
          return prev.map((m) => m.id === streamingId ? finalMsg : m)
        }
        return [...prev, finalMsg]
      })
      streamingId = null
      streamedParts = []
      setIsRunning(false)
      setCurrentActivity(null)
    })

    return () => source.close()
  }, [conversationId])

  const convertMessage = useCallback(
    (msg: Message): ThreadMessageLike => {
      let content: ThreadMessageLike['content']

      // Parse structured content (JSON array of parts) or plain text
      if (msg.role === 'assistant' && msg.content.startsWith('[')) {
        try {
          type Part = { type: string; text?: string; name?: string; input?: Record<string, unknown>; result?: string }
          const parts = JSON.parse(msg.content) as Part[]
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const built: any[] = []
          // Merge consecutive tool_call + tool_result into one tool-call part
          for (let i = 0; i < parts.length; i++) {
            const p = parts[i]
            if (p.type === 'tool_call') {
              const next = parts[i + 1]
              const result = next?.type === 'tool_result' ? next.result : undefined
              if (next?.type === 'tool_result') i++
              built.push({
                type: 'tool-call',
                toolCallId: `${p.name}-${i}`,
                toolName: p.name!,
                args: p.input ?? {},
                result,
              })
            } else {
              built.push({ type: 'text', text: p.text ?? '' })
            }
          }
          content = built
        } catch {
          content = [{ type: 'text', text: msg.content }]
        }
      } else {
        content = [{ type: 'text', text: msg.content }]
      }

      return {
        id: msg.id,
        role: msg.role,
        content,
        ...(msg.role === 'assistant' && msg.agent_name
          ? { metadata: { custom: { agentName: msg.agent_name } } }
          : {}),
      }
    },
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
      if (!backgroundMode) {
        setIsRunning(true)
        setCurrentActivity({ type: 'thinking', text: 'starting...' })
      }

      await fetchJSON('/messages', {
        method: 'POST',
        body: JSON.stringify({
          text,
          thread_id: threadId || 'default',
          ...(backgroundMode ? { background: true } : {}),
        }),
      })

      if (backgroundMode) {
        setBackgroundMode(false) // reset after sending
      }

      onConversationCreated?.()
    },
    [threadId, onConversationCreated, backgroundMode],
  )

  const runtime = useExternalStoreRuntime({
    messages,
    isRunning,
    convertMessage,
    onNew,
  })

  return { runtime, messages, setMessages, currentActivity, backgroundMode, setBackgroundMode }
}
