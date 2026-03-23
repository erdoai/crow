import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchJSON, type Agent, type Conversation } from '../api'
import { useCrowRuntime } from '../hooks/useCrowRuntime'
import { AssistantRuntimeProvider } from '@assistant-ui/react'
import { Thread } from '@/components/assistant-ui/thread'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { MessageSquarePlus } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function ChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const navigate = useNavigate()
  const [agents, setAgents] = useState<Agent[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)

  useEffect(() => {
    fetchJSON<Agent[]>('/agents').then(setAgents)
    fetchJSON<Conversation[]>('/conversations').then(setConversations)
  }, [])

  useEffect(() => {
    if (!conversationId) {
      setThreadId(null)
      return
    }
    const conv = conversations.find(c => c.id === conversationId)
    if (conv) setThreadId(conv.gateway_thread_id)
  }, [conversationId, conversations])

  const refreshConversations = useCallback(() => {
    fetchJSON<Conversation[]>('/conversations').then(setConversations)
  }, [])

  const { runtime } = useCrowRuntime(conversationId ?? null, threadId, refreshConversations)

  async function startChatWithAgent(agentName: string) {
    const newThreadId = `chat-${agentName}-${Date.now()}`
    await fetchJSON('/messages', {
      method: 'POST',
      body: JSON.stringify({ text: `Hi, I'd like to chat with you.`, thread_id: newThreadId, agent: agentName }),
    })
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
            <div className="flex-1 min-h-0">
              <AssistantRuntimeProvider runtime={runtime}>
                <Thread />
              </AssistantRuntimeProvider>
            </div>
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
