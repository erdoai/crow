import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchJSON, type Conversation, type KnowledgeEntry, type UserAgent } from '../api'
import { useCrowRuntime } from '../hooks/useCrowRuntime'
import { useActivityStream } from '../hooks/useActivityStream'
import { AssistantRuntimeProvider, ComposerPrimitive } from '@assistant-ui/react'
import { Thread, ActivityProvider } from '@/components/assistant-ui/thread'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { MessageSquarePlus, Menu, X, Settings, ArrowLeft, ArrowUp, Circle, Brain, Pin, Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { cn } from '@/lib/utils'

function relativeTime(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function getGreeting(): string {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 12) return 'good morning'
  if (hour >= 12 && hour < 17) return 'good afternoon'
  if (hour >= 17 && hour < 21) return 'good evening'
  return 'hey'
}

export default function ChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const navigate = useNavigate()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [userAgent, setUserAgent] = useState<UserAgent | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [knowledge, setKnowledge] = useState<KnowledgeEntry[]>([])
  const [knowledgeOpen, setKnowledgeOpen] = useState(false)
  const [expandedKnowledge, setExpandedKnowledge] = useState<Set<string>>(new Set())
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    Promise.all([
      fetchJSON<Conversation[]>('/conversations').then(setConversations),
      fetchJSON<UserAgent>('/user/agent').then(setUserAgent).catch(() => {}),
      fetchJSON<{ display_name: string }>('/api/me').then(u => setDisplayName(u.display_name || '')).catch(() => {}),
      fetchJSON<KnowledgeEntry[]>('/knowledge').then(setKnowledge).catch(() => {}),
    ]).finally(() => setLoaded(true))
  }, [])

  useEffect(() => {
    if (!conversationId) {
      setThreadId(null)
      return
    }
    const conv = conversations.find(c => c.id === conversationId)
    if (conv) setThreadId(conv.gateway_thread_id)
  }, [conversationId, conversations])

  const [pendingThreadId, setPendingThreadId] = useState<string | null>(null)

  const refreshConversations = useCallback(async () => {
    const convs = await fetchJSON<Conversation[]>('/conversations')
    setConversations(convs)
    if (pendingThreadId && !conversationId) {
      const conv = convs.find(c => c.gateway_thread_id === pendingThreadId)
      if (conv) {
        setPendingThreadId(null)
        navigate(`/chat/${conv.id}`)
      }
    }
  }, [pendingThreadId, conversationId, navigate])

  const activeThreadId = threadId || pendingThreadId
  const { runtime, currentActivity } = useCrowRuntime(conversationId ?? null, activeThreadId, refreshConversations)

  // Background job tracking
  const { jobs } = useActivityStream(true)
  const runningJobs = useMemo(() => jobs.filter(j => j.status === 'running' || j.status === 'pending'), [jobs])
  const activeConversationIds = useMemo(() => {
    const ids = new Set<string>()
    for (const j of runningJobs) {
      if (j.conversation_id) ids.add(j.conversation_id)
      if (j.parent_conversation_id) ids.add(j.parent_conversation_id)
    }
    return ids
  }, [runningJobs])

  useEffect(() => {
    if (!conversationId) {
      setPendingThreadId(`chat-${Date.now()}`)
    }
  }, [conversationId])

  const agentName = userAgent?.agent_name || 'assistant'
  const inChat = !!conversationId
  const soulEntries = useMemo(() => knowledge.filter(k => k.pinned || k.category === 'soul'), [knowledge])
  const otherKnowledge = useMemo(() => knowledge.filter(k => !k.pinned && k.category !== 'soul'), [knowledge])

  function toggleKnowledgeExpand(id: string) {
    setExpandedKnowledge(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function deleteKnowledgeEntry(id: string) {
    await fetchJSON(`/knowledge/${id}`, { method: 'DELETE' })
    setKnowledge(prev => prev.filter(k => k.id !== id))
  }

  if (!loaded && !inChat) return null

  return (
    <div className="flex h-dvh">
      {/* Drawer overlay */}
      {drawerOpen && (
        <div className="fixed inset-0 bg-black/50 z-30" onClick={() => setDrawerOpen(false)} />
      )}

      {/* Conversation drawer — slides from LEFT */}
      <aside className={cn(
        'fixed inset-y-0 left-0 w-72 bg-sidebar border-r border-sidebar-border flex flex-col z-40',
        'transition-transform duration-200 ease-in-out',
        drawerOpen ? 'translate-x-0' : '-translate-x-full'
      )}>
        <div className="p-4 flex items-center justify-between border-b border-sidebar-border">
          <span className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">conversations</span>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" onClick={() => { navigate('/'); setDrawerOpen(false) }}>
              <MessageSquarePlus className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setDrawerOpen(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <ScrollArea className="flex-1">
          {/* Running / pending background jobs */}
          {runningJobs.length > 0 && (
            <div className="px-3 py-2 border-b border-sidebar-border">
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">running</span>
              <div className="flex flex-col gap-1 mt-1">
                {runningJobs.map(j => (
                  <div key={j.id} className="flex items-center gap-1.5 text-xs text-sidebar-foreground">
                    <span className="relative flex h-2 w-2 shrink-0">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-500 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
                    </span>
                    <span className="truncate">{j.input?.slice(0, 40) || j.agent_name}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-col gap-0.5 p-1.5">
            {conversations.map(c => (
              <button
                key={c.id}
                className={cn(
                  'w-full text-left px-3 py-2 rounded-md text-sm transition-colors',
                  c.id === conversationId
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent/50'
                )}
                onClick={() => { navigate(`/chat/${c.id}`); setDrawerOpen(false) }}
              >
                <div className="flex items-center gap-1.5 truncate text-sm">
                  {activeConversationIds.has(c.id) && (
                    <Circle className="h-2 w-2 shrink-0 fill-green-500 text-green-500" />
                  )}
                  <span className="truncate">{c.title || 'untitled'}</span>
                </div>
                {c.updated_at && (
                  <div className="text-[11px] text-muted-foreground">{relativeTime(c.updated_at)}</div>
                )}
              </button>
            ))}
            {conversations.length === 0 && (
              <p className="text-sm text-muted-foreground px-3 py-2">no conversations yet</p>
            )}
          </div>
        </ScrollArea>
      </aside>

      {/* Main area */}
      <main className="flex-1 flex flex-col bg-background min-w-0">
        <AssistantRuntimeProvider runtime={runtime}>
          <ActivityProvider activity={currentActivity}>
            {inChat ? (
              <>
                <div className="px-3 py-3 border-b bg-card font-semibold text-sm flex items-center gap-2 sm:px-6">
                  <Button variant="ghost" size="icon" className="shrink-0" onClick={() => navigate('/')}>
                    <ArrowLeft className="h-4 w-4" />
                  </Button>
                  <span className="truncate flex-1">
                    {conversations.find(c => c.id === conversationId)?.title || agentName}
                  </span>
                  <Button variant="ghost" size="icon" className="shrink-0 relative" onClick={() => setDrawerOpen(true)}>
                    <Menu className="h-4 w-4" />
                    {runningJobs.length > 0 && (
                      <span className="absolute -top-0.5 -right-0.5 h-3.5 w-3.5 rounded-full bg-green-500 text-[9px] font-bold text-white flex items-center justify-center">
                        {runningJobs.length}
                      </span>
                    )}
                  </Button>
                </div>
                <div className="flex-1 min-h-0">
                  <Thread agentName={agentName} userName={displayName} />
                </div>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center p-8 relative">
                {/* Top bar */}
                <div className="absolute top-3 left-3 right-3 flex items-center justify-between">
                  <Button variant="ghost" size="icon" className="relative" onClick={() => setDrawerOpen(true)}>
                    <Menu className="h-5 w-5" />
                    {runningJobs.length > 0 && (
                      <span className="absolute -top-0.5 -right-0.5 h-3.5 w-3.5 rounded-full bg-green-500 text-[9px] font-bold text-white flex items-center justify-center">
                        {runningJobs.length}
                      </span>
                    )}
                  </Button>
                  <div className="flex items-center gap-1">
                    <ThemeToggle />
                    <Button variant="ghost" size="icon" onClick={() => navigate('/settings')}>
                      <Settings className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <div className="w-full max-w-2xl flex flex-col items-center gap-6">
                  <div className="text-center">
                    <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
                      <span className="text-2xl font-bold text-primary">
                        {agentName.charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <h1 className="text-2xl font-semibold tracking-tight">{agentName}</h1>
                    <p className="text-sm text-muted-foreground mt-1">
                      {getGreeting()}, {displayName || 'there'}. what can I help with?
                    </p>
                  </div>

                  {/* Home composer */}
                  <HomeComposer />

                  {/* Knowledge surface — what your agent knows */}
                  {knowledge.length > 0 && (
                    <div className="w-full mt-2">
                      <button
                        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mx-auto"
                        onClick={() => setKnowledgeOpen(!knowledgeOpen)}
                      >
                        <Brain className="h-3.5 w-3.5" />
                        <span>{knowledge.length} thing{knowledge.length !== 1 ? 's' : ''} {agentName} knows</span>
                        {knowledgeOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                      </button>

                      {knowledgeOpen && (
                        <div className="mt-3 flex flex-col gap-2">
                          {/* Soul/pinned entries first */}
                          {soulEntries.length > 0 && (
                            <div className="bg-primary/5 border border-primary/15 rounded-lg overflow-hidden">
                              <div className="px-3 py-2 flex items-center gap-1.5">
                                <Pin className="h-3 w-3 text-primary" />
                                <span className="text-[10px] font-semibold uppercase tracking-wider text-primary/70">identity</span>
                              </div>
                              <div className="divide-y divide-primary/10">
                                {soulEntries.map(k => (
                                  <KnowledgeItem
                                    key={k.id}
                                    entry={k}
                                    expanded={expandedKnowledge.has(k.id)}
                                    onToggle={() => toggleKnowledgeExpand(k.id)}
                                    onDelete={() => deleteKnowledgeEntry(k.id)}
                                  />
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Other knowledge */}
                          {otherKnowledge.length > 0 && (
                            <div className="bg-card border rounded-lg overflow-hidden divide-y">
                              {otherKnowledge.map(k => (
                                <KnowledgeItem
                                  key={k.id}
                                  entry={k}
                                  expanded={expandedKnowledge.has(k.id)}
                                  onToggle={() => toggleKnowledgeExpand(k.id)}
                                  onDelete={() => deleteKnowledgeEntry(k.id)}
                                />
                              ))}
                            </div>
                          )}

                          {knowledge.length === 0 && (
                            <p className="text-xs text-muted-foreground text-center">
                              {agentName} will learn about you as you talk. ask questions, share context, and they'll remember.
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Nudge if no knowledge yet */}
                  {knowledge.length === 0 && (
                    <p className="text-xs text-muted-foreground text-center max-w-sm">
                      {agentName} is brand new — they don't know anything about you yet. start a conversation and they'll learn.
                    </p>
                  )}
                </div>
              </div>
            )}
          </ActivityProvider>
        </AssistantRuntimeProvider>
      </main>
    </div>
  )
}

function KnowledgeItem({ entry, expanded, onToggle, onDelete }: {
  entry: KnowledgeEntry
  expanded: boolean
  onToggle: () => void
  onDelete: () => void
}) {
  return (
    <div className="group">
      <button
        className="w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-muted/30 transition-colors"
        onClick={onToggle}
      >
        {expanded ? <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />}
        <span className="text-sm truncate flex-1">{entry.title}</span>
        <span className="text-[10px] text-muted-foreground shrink-0">{entry.category}</span>
      </button>
      {expanded && (
        <div className="px-3 pb-2 pl-8">
          <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">{entry.content}</p>
          <div className="flex items-center justify-between mt-2">
            {entry.updated_at && (
              <span className="text-[10px] text-muted-foreground">{relativeTime(entry.updated_at)}</span>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-[10px] text-destructive hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
              onClick={(e) => { e.stopPropagation(); onDelete() }}
            >
              <Trash2 className="h-3 w-3 mr-1" />
              delete
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function HomeComposer() {
  return (
    <ComposerPrimitive.Root className="w-full flex gap-2 items-end">
      <ComposerPrimitive.Input
        placeholder="Message..."
        autoFocus
        className={cn(
          'flex-1 rounded-xl border border-input bg-background px-4 py-4 text-base min-h-[4rem] resize-none',
          'placeholder:text-muted-foreground',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        )}
      />
      <ComposerPrimitive.Send asChild>
        <Button size="icon" className="rounded-full shrink-0 h-10 w-10">
          <ArrowUp className="h-4 w-4" />
        </Button>
      </ComposerPrimitive.Send>
    </ComposerPrimitive.Root>
  )
}
