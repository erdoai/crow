import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchJSON, type Agent, type Conversation, type Message } from '../api'
import { useSSE } from '../hooks/useSSE'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { ArrowUp, MessageSquarePlus, Cpu } from 'lucide-react'
import { cn } from '@/lib/utils'

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
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchJSON<Agent[]>('/agents').then(setAgents)
    fetchJSON<Conversation[]>('/conversations').then(setConversations)
  }, [])

  useEffect(() => {
    if (!conversationId) {
      setMessages([])
      setThreadId(null)
      return
    }
    fetchJSON<Message[]>(`/conversations/${conversationId}/messages`).then(setMessages)
    const conv = conversations.find(c => c.id === conversationId)
    if (conv) setThreadId(conv.gateway_thread_id)
  }, [conversationId, conversations])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, typing])

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
    inputRef.current?.focus()
  }

  async function startChatWithAgent(agentName: string) {
    const newThreadId = `chat-${agentName}-${Date.now()}`
    await fetchJSON('/messages', {
      method: 'POST',
      body: JSON.stringify({ text: `Hi, I'd like to chat with you.`, thread_id: newThreadId, agent: agentName }),
    })
    // Poll for conversation
    const poll = async (attempts = 0): Promise<void> => {
      const convs = await fetchJSON<Conversation[]>('/conversations')
      setConversations(convs)
      const conv = convs.find(c => c.gateway_thread_id === newThreadId)
      if (conv) {
        navigate(`/chat/${conv.id}`)
      } else if (attempts < 5) {
        await new Promise(r => setTimeout(r, 500))
        return poll(attempts + 1)
      } else {
        navigate('/chat')
      }
    }
    await poll()
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(e)
    }
  }

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="w-72 min-w-72 bg-sidebar border-r border-sidebar-border flex flex-col">
        <div className="p-4 flex items-center justify-between border-b border-sidebar-border">
          <button
            onClick={() => navigate('/dashboard')}
            className="text-lg font-bold tracking-tight text-primary no-underline"
          >
            crow
          </button>
          <Button variant="ghost" size="icon" onClick={() => navigate('/chat')}>
            <MessageSquarePlus className="h-4 w-4" />
          </Button>
        </div>

        <div className="p-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">agents</p>
          <div className="flex flex-wrap gap-1.5">
            {agents.map(agent => (
              <Badge
                key={agent.name}
                variant="outline"
                className="cursor-pointer hover:bg-primary hover:text-primary-foreground transition-colors"
                onClick={() => startChatWithAgent(agent.name)}
              >
                {agent.name}
              </Badge>
            ))}
          </div>
        </div>

        <Separator />

        <div className="p-3 flex-1 overflow-hidden flex flex-col">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">conversations</p>
          <ScrollArea className="flex-1">
            <div className="flex flex-col gap-0.5">
              {conversations.map(c => (
                <button
                  key={c.id}
                  className={cn(
                    'w-full text-left px-3 py-2 rounded-md text-sm transition-colors',
                    c.id === conversationId
                      ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                      : 'text-sidebar-foreground hover:bg-sidebar-accent/50'
                  )}
                  onClick={() => navigate(`/chat/${c.id}`)}
                >
                  <div className="truncate">{c.gateway_thread_id}</div>
                  {c.updated_at && (
                    <div className="text-xs text-muted-foreground">
                      {new Date(c.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    </div>
                  )}
                </button>
              ))}
              {conversations.length === 0 && (
                <p className="text-sm text-muted-foreground px-3 py-2">no conversations yet</p>
              )}
            </div>
          </ScrollArea>
        </div>
      </aside>

      {/* Chat */}
      <main className="flex-1 flex flex-col bg-background">
        {conversationId ? (
          <>
            <div className="px-6 py-3 border-b bg-card font-semibold text-sm">
              {threadId}
            </div>
            <ScrollArea className="flex-1 px-6 py-4">
              <div className="flex flex-col gap-1 max-w-3xl mx-auto">
                {messages.map(msg => (
                  <div
                    key={msg.id}
                    className={cn('flex flex-col max-w-[70%]', msg.role === 'user' ? 'self-end items-end' : 'self-start items-start')}
                  >
                    {msg.role !== 'user' && msg.agent_name && (
                      <div className="flex items-center gap-1 text-xs text-muted-foreground mb-0.5 pl-3">
                        <Cpu className="h-3 w-3" />
                        {msg.agent_name}
                      </div>
                    )}
                    <div className={cn(
                      'px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap',
                      msg.role === 'user'
                        ? 'bg-primary text-primary-foreground rounded-br-sm'
                        : 'bg-card border border-border rounded-bl-sm'
                    )}>
                      {msg.content}
                    </div>
                  </div>
                ))}
                {typing && (
                  <div className="self-start">
                    <div className="bg-card border border-border rounded-2xl rounded-bl-sm px-4 py-3 flex gap-1">
                      <span className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce [animation-delay:0ms]" />
                      <span className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce [animation-delay:150ms]" />
                      <span className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce [animation-delay:300ms]" />
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            </ScrollArea>
            <form className="px-6 py-3 border-t bg-card flex gap-2 items-end" onSubmit={sendMessage}>
              <Input
                ref={inputRef}
                placeholder="Message..."
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                autoFocus
                className="rounded-full"
              />
              <Button type="submit" size="icon" className="rounded-full shrink-0" disabled={!input.trim()}>
                <ArrowUp className="h-4 w-4" />
              </Button>
            </form>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-muted-foreground">
            <MessageSquarePlus className="h-12 w-12 opacity-30" />
            <p>select a conversation or click an agent to start chatting</p>
          </div>
        )}
      </main>
    </div>
  )
}
