import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchJSON, type Agent, type Conversation } from '../api'
import { useCrowRuntime } from '../hooks/useCrowRuntime'
import { useActivityStream } from '../hooks/useActivityStream'
import { AssistantRuntimeProvider } from '@assistant-ui/react'
import { Thread, ActivityProvider } from '@/components/assistant-ui/thread'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { MessageSquarePlus, ChevronDown, ChevronRight, Menu, X, Circle } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import ActivitySection from '@/components/activity/ActivitySection'
import StoreSection from '@/components/store/StoreSection'
import { useJobNotifications } from '../hooks/useJobNotifications'
import { cn } from '@/lib/utils'

function relativeTime(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function ChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const navigate = useNavigate()
  const [agents, setAgents] = useState<Agent[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)
  const [agentsExpanded, setAgentsExpanded] = useState(true)
  const [convosExpanded, setConvosExpanded] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Always-on activity stream
  const { jobs, scheduledJobs, workers, cancelScheduledJob } = useActivityStream(true)

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

  const { runtime, currentActivity, backgroundMode, setBackgroundMode } = useCrowRuntime(conversationId ?? null, threadId, refreshConversations)

  // Toast + browser notifications for job status changes
  useJobNotifications(jobs, conversationId ?? null)

  // Conversations with running/pending jobs (including bg jobs via parent_conversation_id)
  const activeConversationIds = useMemo(() => {
    const ids = new Set<string>()
    for (const j of jobs) {
      if (j.status !== 'running' && j.status !== 'pending') continue
      if (j.conversation_id) ids.add(j.conversation_id)
      if (j.parent_conversation_id) ids.add(j.parent_conversation_id)
    }
    return ids
  }, [jobs])

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

  // Close sidebar when navigating to a conversation on mobile
  const navigateAndCloseSidebar = useCallback((path: string) => {
    navigate(path)
    setSidebarOpen(false)
  }, [navigate])

  return (
    <div className="flex h-dvh">
      {/* Mobile overlay backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={cn(
        'bg-sidebar border-r border-sidebar-border flex flex-col z-40',
        // Mobile: full-screen overlay drawer
        'fixed inset-y-0 left-0 w-72 transition-transform duration-200 ease-in-out lg:relative lg:translate-x-0 lg:min-w-72',
        sidebarOpen ? 'translate-x-0' : '-translate-x-full'
      )}>
        {/* Header */}
        <div className="p-4 flex items-center justify-between border-b border-sidebar-border">
          <button
            onClick={() => navigateAndCloseSidebar('/dashboard')}
            className="text-lg font-bold tracking-tight text-primary no-underline"
          >
            crow
          </button>
          <div className="flex items-center">
            <ThemeToggle />
            <Button variant="ghost" size="icon" onClick={() => { navigate('/chat'); setSidebarOpen(false) }}>
              <MessageSquarePlus className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setSidebarOpen(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Agents section */}
        <div>
          <button
            className="w-full px-3 py-2 flex items-center gap-1.5 hover:bg-sidebar-accent/50 transition-colors"
            onClick={() => setAgentsExpanded(e => !e)}
          >
            {agentsExpanded
              ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
              : <ChevronRight className="h-3 w-3 text-muted-foreground" />
            }
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">agents</span>
          </button>
          {agentsExpanded && (
            <div className="px-3 pb-2 flex flex-wrap gap-1.5">
              {agents.map(agent => (
                <Badge
                  key={agent.name}
                  variant="outline"
                  className="cursor-pointer hover:bg-primary hover:text-primary-foreground transition-colors"
                  onClick={() => { startChatWithAgent(agent.name); setSidebarOpen(false) }}
                >
                  {agent.name}
                </Badge>
              ))}
            </div>
          )}
        </div>

        <Separator />

        {/* Activity section */}
        <ActivitySection
          jobs={jobs}
          scheduledJobs={scheduledJobs}
          workers={workers}
          cancelScheduledJob={cancelScheduledJob}
        />

        <Separator />

        {/* Store section */}
        <StoreSection />

        <Separator />

        {/* Conversations section */}
        <div className="flex-1 overflow-hidden flex flex-col min-h-0">
          <button
            className="w-full px-3 py-2 flex items-center gap-1.5 hover:bg-sidebar-accent/50 transition-colors shrink-0"
            onClick={() => setConvosExpanded(e => !e)}
          >
            {convosExpanded
              ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
              : <ChevronRight className="h-3 w-3 text-muted-foreground" />
            }
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">conversations</span>
          </button>
          {convosExpanded && (
            <ScrollArea className="flex-1">
              <div className="flex flex-col gap-0.5 px-1.5 pb-2">
                {conversations.map(c => (
                  <button
                    key={c.id}
                    className={cn(
                      'w-full text-left px-3 py-2 rounded-md text-sm transition-colors',
                      c.id === conversationId
                        ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                        : 'text-sidebar-foreground hover:bg-sidebar-accent/50'
                    )}
                    onClick={() => navigateAndCloseSidebar(`/chat/${c.id}`)}
                  >
                    <div className="flex items-center gap-1.5 truncate text-sm">
                      {activeConversationIds.has(c.id) && (
                        <Circle className="h-2 w-2 shrink-0 fill-green-500 text-green-500" />
                      )}
                      <span className="truncate">{c.title || c.gateway_thread_id}</span>
                    </div>
                    {c.updated_at && (
                      <div
                        className="text-[11px] text-muted-foreground"
                        title={new Date(c.updated_at).toLocaleString()}
                      >
                        {relativeTime(c.updated_at)}
                      </div>
                    )}
                  </button>
                ))}
                {conversations.length === 0 && (
                  <p className="text-sm text-muted-foreground px-3 py-2">no conversations yet</p>
                )}
              </div>
            </ScrollArea>
          )}
        </div>
      </aside>

      {/* Chat */}
      <main className="flex-1 flex flex-col bg-background min-w-0">
        {conversationId ? (
          <>
            <div className="px-3 py-3 border-b bg-card font-semibold text-sm flex items-center gap-2 sm:px-6">
              <Button variant="ghost" size="icon" className="lg:hidden shrink-0" onClick={() => setSidebarOpen(true)}>
                <Menu className="h-4 w-4" />
              </Button>
              <span className="truncate">{conversations.find(c => c.id === conversationId)?.title || threadId}</span>
            </div>
            <div className="flex-1 min-h-0">
              <AssistantRuntimeProvider runtime={runtime}>
                <ActivityProvider
                  activity={currentActivity}
                  backgroundMode={backgroundMode}
                  onToggleBackground={() => setBackgroundMode(b => !b)}
                >
                  <Thread />
                </ActivityProvider>
              </AssistantRuntimeProvider>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center p-8">
            <Button variant="ghost" size="icon" className="lg:hidden absolute top-3 left-3" onClick={() => setSidebarOpen(true)}>
              <Menu className="h-5 w-5" />
            </Button>
            <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
              <MessageSquarePlus className="h-8 w-8 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-foreground">start a conversation</h2>
              <p className="text-sm text-muted-foreground mt-1 max-w-xs">
                pick an agent from the sidebar, or open an existing conversation
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
