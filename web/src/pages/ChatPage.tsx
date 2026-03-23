import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchJSON, type Agent, type Conversation, type Message } from '../api'
import { useSSE } from '../hooks/useSSE'

export default function ChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const navigate = useNavigate()
  const [agents, setAgents] = useState<Agent[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Load sidebar data
  useEffect(() => {
    fetchJSON<Agent[]>('/agents').then(setAgents)
    fetchJSON<Conversation[]>('/conversations').then(setConversations)
  }, [])

  // Load messages when conversation changes
  useEffect(() => {
    if (!conversationId) {
      setMessages([])
      setThreadId(null)
      return
    }
    fetchJSON<Message[]>(`/conversations/${conversationId}/messages`).then(setMessages)
    // Get thread ID from conversation
    const conv = conversations.find(c => c.id === conversationId)
    if (conv) setThreadId(conv.gateway_thread_id)
  }, [conversationId, conversations])

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, typing])

  // SSE for real-time messages
  const handleSSE = useCallback((data: { text: string; agent_name: string | null }) => {
    setMessages(prev => [...prev, {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: data.text,
      agent_name: data.agent_name,
    }])
    setTyping(false)
  }, [])

  useSSE(conversationId ?? null, handleSSE)

  async function sendMessage(e: React.FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text) return
    setInput('')

    // Optimistic update
    setMessages(prev => [...prev, {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      agent_name: null,
    }])
    setTyping(true)

    await fetchJSON('/messages', {
      method: 'POST',
      body: JSON.stringify({ text, thread_id: threadId || 'default' }),
    })
  }

  async function startChatWithAgent(agentName: string) {
    const newThreadId = `chat-${agentName}-${Date.now()}`
    await fetchJSON('/messages', {
      method: 'POST',
      body: JSON.stringify({ text: "Hi, I'd like to chat with you.", thread_id: newThreadId, agent: agentName }),
    })
    setTimeout(async () => {
      const convs = await fetchJSON<Conversation[]>('/conversations')
      setConversations(convs)
      const conv = convs.find(c => c.gateway_thread_id === newThreadId)
      navigate(conv ? `/chat/${conv.id}` : '/chat')
    }, 1000)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(e)
    }
  }

  return (
    <div className="chat-layout">
      {/* Sidebar */}
      <aside className="chat-sidebar">
        <div className="sidebar-header">
          <a href="/dashboard" className="sidebar-logo" onClick={e => { e.preventDefault(); navigate('/dashboard') }}>crow</a>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/chat')}>+</button>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-label">agents</div>
          <div className="agent-chips">
            {agents.map(agent => (
              <button
                key={agent.name}
                className="agent-chip"
                onClick={() => startChatWithAgent(agent.name)}
                title={agent.description}
              >
                {agent.name}
              </button>
            ))}
          </div>
        </div>

        <div className="sidebar-section sidebar-conversations">
          <div className="sidebar-label">conversations</div>
          <div>
            {conversations.map(c => (
              <a
                key={c.id}
                href={`/chat/${c.id}`}
                className={`conv-item${c.id === conversationId ? ' active' : ''}`}
                onClick={e => { e.preventDefault(); navigate(`/chat/${c.id}`) }}
              >
                <span className="conv-thread">{c.gateway_thread_id}</span>
                <span className="conv-time">
                  {c.updated_at ? new Date(c.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''}
                </span>
              </a>
            ))}
            {conversations.length === 0 && (
              <div className="conv-empty">no conversations yet</div>
            )}
          </div>
        </div>
      </aside>

      {/* Chat area */}
      <main className="chat-main">
        {conversationId ? (
          <>
            <div className="chat-header">
              <span className="chat-thread-name">{threadId}</span>
            </div>
            <div className="chat-messages">
              {messages.map(msg => (
                <div key={msg.id} className={`message ${msg.role === 'user' ? 'user' : 'assistant'}`}>
                  {msg.role !== 'user' && msg.agent_name && (
                    <div className="msg-agent">{msg.agent_name}</div>
                  )}
                  <div className="msg-bubble">{msg.content}</div>
                </div>
              ))}
              {typing && (
                <div className="message assistant">
                  <div className="msg-bubble typing">
                    <span className="dot"></span>
                    <span className="dot"></span>
                    <span className="dot"></span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <form className="chat-input-bar" onSubmit={sendMessage}>
              <input
                type="text"
                className="chat-input"
                placeholder="Message..."
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                autoFocus
              />
              <button type="submit" className="chat-send-btn">&uarr;</button>
            </form>
          </>
        ) : (
          <div className="chat-empty">
            <div className="chat-empty-icon">&#x1f4ac;</div>
            <div className="chat-empty-text">select a conversation or click an agent to start chatting</div>
          </div>
        )}
      </main>
    </div>
  )
}
