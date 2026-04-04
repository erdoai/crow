import { useState, useCallback, useEffect, useMemo } from 'react'
import {
  useExternalStoreRuntime,
  type ThreadMessageLike,
  type AppendMessage,
} from '@assistant-ui/react'
import { fetchJSON, type Message, type ContentPart } from '../api'
import { hasRenderer } from '../renderers/registry'

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
      setIsRunning(false)
      setCurrentActivity(null)
      return
    }
    // Don't reset isRunning here — if we just navigated from the home screen
    // after sending a message, the agent is still working. SSE events will
    // set isRunning=false when the job completes.
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
      const content = [...streamedParts]
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

      const content = [...streamedParts]
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

    source.addEventListener('error', (e) => {
      if (!(e instanceof MessageEvent)) return
      const data = JSON.parse(e.data) as {
        error: string
        agent_name: string | null
        job_id: string
      }
      // Show the error as a final assistant message
      const id = streamingId || `error-${data.job_id}`
      const errorMsg: Message = {
        id,
        role: 'assistant',
        content: [{ type: 'text', text: `Error: ${data.error}` }],
        agent_name: data.agent_name,
      }
      setMessages((prev) => {
        if (streamingId) {
          return prev.map((m) => m.id === streamingId ? errorMsg : m)
        }
        return [...prev, errorMsg]
      })
      streamingId = null
      streamedParts = []
      setIsRunning(false)
      setCurrentActivity(null)
    })

    source.addEventListener('message', (e) => {
      const data = JSON.parse(e.data) as {
        text: string | ContentPart[]
        agent_name: string | null
        timestamp: string
        event_id: string
      }
      if (streamingId) {
        // Chat job completed. The turns are already persisted via
        // _save_turn — reload from DB to get the canonical messages
        // and drop the ephemeral streaming message.
        fetchJSON<Message[]>(`/conversations/${conversationId}/messages`).then(setMessages)
        streamingId = null
        streamedParts = []
        setIsRunning(false)
        setCurrentActivity(null)
      } else {
        // post_update or bg job result — append if not already present
        setMessages((prev) => {
          if (prev.some((m) => m.id === data.event_id)) return prev
          const msg: Message = {
            id: data.event_id,
            role: 'assistant',
            content: data.text,
            agent_name: data.agent_name,
          }
          return [...prev, msg]
        })
      }
    })

    return () => source.close()
  }, [conversationId])

  const convertMessage = useCallback(
    (msg: Message): ThreadMessageLike => {
      let content: ThreadMessageLike['content']

      // Collect custom content parts (chart, etc.) for pluggable renderers
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const richParts: Record<string, any>[] = []

      if (msg.role === 'assistant' && Array.isArray(msg.content)) {
        // Structured content from JSONB — map to assistant-ui format
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const built: any[] = []
        const parts = msg.content
        for (let i = 0; i < parts.length; i++) {
          const p = parts[i]
          if (p.type === 'tool_call' || p.type === 'tool_use') {
            const next = parts[i + 1]
            const result = next?.type === 'tool_result' ? (next.result ?? next.content) : undefined
            if (next?.type === 'tool_result') i++
            const name = p.name!
            const input = p.input ?? {}
            // Render status tools as inline text, not tool cards
            if (name === 'progress_update') {
              const status = (input as Record<string, unknown>).status
              if (status) built.push({ type: 'text', text: `*${status}*` })
              continue
            }
            if (name === 'post_update') continue // notification only
            built.push({
              type: 'tool-call',
              toolCallId: p.id ?? `${name}-${i}`,
              toolName: name,
              args: input,
              result,
            })
          } else if (p.type === 'tool_result') {
            continue
          } else if (hasRenderer(p.type)) {
            richParts.push(p)
          } else if (p.text?.trim()) {
            built.push({ type: 'text', text: p.text })
          }
        }
        content = built.length > 0 ? built : [{ type: 'text', text: '' }]
      } else {
        const text = typeof msg.content === 'string' ? msg.content : ''
        content = [{ type: 'text', text }]
      }

      const custom: Record<string, unknown> = {}
      if (msg.role === 'assistant' && msg.agent_name) custom.agentName = msg.agent_name
      if (richParts.length > 0) custom.richParts = richParts

      return {
        id: msg.id,
        role: msg.role,
        content,
        ...(Object.keys(custom).length > 0 ? { metadata: { custom } } : {}),
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

  // Filter out internal messages that shouldn't render:
  // - user-role tool_result turns (API format, array content)
  // - [spawn_job result: ...] handoff messages
  const visibleMessages = useMemo(() => messages.filter((m) => {
    if (m.role === 'user' && Array.isArray(m.content)) return false
    if (m.role === 'user' && typeof m.content === 'string' && m.content.startsWith('[spawn_job result:')) return false
    return true
  }), [messages])

  const runtime = useExternalStoreRuntime({
    messages: visibleMessages,
    isRunning,
    convertMessage,
    onNew,
  })

  return { runtime, messages, setMessages, currentActivity, backgroundMode, setBackgroundMode }
}
