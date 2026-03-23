import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchJSON, type Conversation, type DashboardData } from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LogOut, Key, Brain, MessageSquare, Cpu } from 'lucide-react'

export default function DashboardPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardData | null>(null)
  const [keyName, setKeyName] = useState('')
  const [newKey, setNewKey] = useState('')

  useEffect(() => {
    fetchJSON<DashboardData>('/api/dashboard').then(setData)
  }, [])

  async function createApiKey(e: React.FormEvent) {
    e.preventDefault()
    if (!keyName.trim()) return
    const res = await fetchJSON<{ id: string; key: string; prefix: string }>('/dashboard/api-keys', {
      method: 'POST',
      body: JSON.stringify({ name: keyName.trim() }),
    })
    setNewKey(res.key)
    setKeyName('')
    fetchJSON<DashboardData>('/api/dashboard').then(setData)
  }

  async function deleteApiKey(keyId: string) {
    if (!confirm('revoke this API key?')) return
    await fetchJSON(`/dashboard/api-keys/${keyId}`, { method: 'DELETE' })
    fetchJSON<DashboardData>('/api/dashboard').then(setData)
  }

  async function startChatWithAgent(agentName: string) {
    const threadId = `chat-${agentName}-${Date.now()}`
    await fetchJSON('/messages', {
      method: 'POST',
      body: JSON.stringify({ text: `Hi, I'd like to chat with you.`, thread_id: threadId, agent: agentName }),
    })
    const poll = async (attempts = 0): Promise<void> => {
      const convs = await fetchJSON<Conversation[]>('/conversations')
      const conv = convs.find(c => c.gateway_thread_id === threadId)
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

  async function logout() {
    await fetch('/auth/logout', { method: 'POST' })
    window.location.href = '/login'
  }

  if (!data) return null

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="bg-primary text-primary-foreground px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-tight">crow</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm opacity-90">hi, {data.display_name}</span>
          <Button variant="ghost" size="sm" onClick={() => navigate('/chat')} className="text-primary-foreground/70 hover:text-primary-foreground hover:bg-white/10">
            <MessageSquare className="h-4 w-4 mr-1" /> chat
          </Button>
          {data.auth_enabled && (
            <Button variant="ghost" size="sm" onClick={logout} className="text-primary-foreground/70 hover:text-primary-foreground hover:bg-white/10">
              <LogOut className="h-4 w-4" />
            </Button>
          )}
        </div>
      </header>

      <main className="max-w-3xl mx-auto p-6 flex flex-col gap-8">
        {/* Agents */}
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
            <Cpu className="h-3.5 w-3.5" /> agents
          </h2>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
            {data.agents.map(agent => (
              <Card
                key={agent.name}
                className="cursor-pointer hover:border-primary/30 transition-colors"
                onClick={() => startChatWithAgent(agent.name)}
              >
                <CardHeader className="p-4">
                  <CardTitle className="text-base text-primary">{agent.name}</CardTitle>
                  <CardDescription>{agent.description}</CardDescription>
                </CardHeader>
              </Card>
            ))}
            {data.agents.length === 0 && <p className="text-sm text-muted-foreground">no agents configured</p>}
          </div>
        </section>

        {/* API Keys */}
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
            <Key className="h-3.5 w-3.5" /> API keys
          </h2>
          {data.api_keys.length > 0 && (
            <div className="bg-card border rounded-lg mb-3 divide-y">
              {data.api_keys.map(key => (
                <div key={key.id} className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{key.name}</span>
                    <code className="text-xs text-muted-foreground">{key.key_prefix}...</code>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => deleteApiKey(key.id)}>revoke</Button>
                </div>
              ))}
            </div>
          )}
          {newKey && (
            <div className="bg-primary/5 border border-primary/20 rounded-lg p-3 mb-3 font-mono text-xs break-all">
              copy this key now (it won't be shown again): {newKey}
            </div>
          )}
          <form className="flex gap-2 items-center" onSubmit={createApiKey}>
            <Input placeholder="key name" value={keyName} onChange={e => setKeyName(e.target.value)} className="max-w-xs" />
            <Button type="submit" variant="secondary" size="sm">create key</Button>
          </form>
        </section>

        {/* Knowledge */}
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
            <Brain className="h-3.5 w-3.5" /> knowledge
          </h2>
          {data.knowledge.length > 0 ? (
            <div className="bg-card border rounded-lg divide-y">
              {data.knowledge.map(k => (
                <div key={k.id} className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{k.category}</Badge>
                    <span className="text-sm">{k.title}</span>
                  </div>
                  <span className="text-xs text-muted-foreground">{k.agent_name}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">no knowledge entries yet</p>
          )}
        </section>

        {/* Recent Conversations */}
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
            <MessageSquare className="h-3.5 w-3.5" /> recent conversations
          </h2>
          {data.conversations.length > 0 ? (
            <div className="bg-card border rounded-lg divide-y">
              {data.conversations.map(c => (
                <button
                  key={c.id}
                  className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-accent/50 transition-colors"
                  onClick={() => navigate(`/chat/${c.id}`)}
                >
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{c.gateway}</Badge>
                    <code className="text-sm">{c.gateway_thread_id}</code>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {c.updated_at ? new Date(c.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">no conversations yet</p>
          )}
        </section>
      </main>
    </div>
  )
}
