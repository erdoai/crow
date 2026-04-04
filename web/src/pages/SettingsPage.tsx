import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchJSON, type DashboardData, type KnowledgeEntry, type Skill } from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ArrowLeft, Key, Brain, Cpu, LogOut, Save, Pin, Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { cn } from '@/lib/utils'

function relativeTime(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function SettingsPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardData | null>(null)
  const [skills, setSkills] = useState<Skill[]>([])
  const [knowledge, setKnowledge] = useState<KnowledgeEntry[]>([])
  const [expandedKnowledge, setExpandedKnowledge] = useState<Set<string>>(new Set())
  const [keyName, setKeyName] = useState('')
  const [newKey, setNewKey] = useState('')

  // Agent name editing
  const [agentName, setAgentName] = useState('')
  const [agentDirty, setAgentDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchJSON<DashboardData>('/api/dashboard').then(d => {
      setData(d)
      if (d.user_agent) {
        setAgentName(d.user_agent.agent_name)
      }
    })
    fetchJSON<Skill[]>('/skills').then(setSkills).catch(() => {})
    fetchJSON<KnowledgeEntry[]>('/knowledge').then(setKnowledge).catch(() => {})
  }, [])

  async function saveAgent() {
    setSaving(true)
    try {
      await fetchJSON('/user/agent', {
        method: 'PUT',
        body: JSON.stringify({ agent_name: agentName.trim() }),
      })
      setAgentDirty(false)
    } finally {
      setSaving(false)
    }
  }

  async function deleteKnowledgeEntry(id: string) {
    await fetchJSON(`/knowledge/${id}`, { method: 'DELETE' })
    setKnowledge(prev => prev.filter(k => k.id !== id))
  }

  function toggleKnowledgeExpand(id: string) {
    setExpandedKnowledge(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

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

  async function logout() {
    await fetch('/auth/logout', { method: 'POST' })
    window.location.href = '/login'
  }

  if (!data) return null

  const soulEntries = knowledge.filter(k => k.pinned || k.category === 'soul')
  const otherEntries = knowledge.filter(k => !k.pinned && k.category !== 'soul')

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-background border-b px-4 py-3 flex items-center justify-between gap-2 sm:px-6 sm:py-4">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={() => navigate('/')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-lg font-semibold tracking-tight">settings</h1>
        </div>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          {data.auth_enabled && (
            <Button variant="ghost" size="sm" onClick={logout} className="text-muted-foreground hover:text-foreground">
              <LogOut className="h-4 w-4" />
            </Button>
          )}
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-4 sm:p-6 flex flex-col gap-6 sm:gap-8">
        {/* Agent */}
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
            <Cpu className="h-3.5 w-3.5" /> your agent
          </h2>
          <div className="bg-card border rounded-lg p-4 flex flex-col gap-3">
            <div>
              <label className="text-sm font-medium" htmlFor="agent-name">name</label>
              <Input
                id="agent-name"
                value={agentName}
                onChange={e => { setAgentName(e.target.value); setAgentDirty(true) }}
                className="mt-1"
              />
            </div>
            <p className="text-xs text-muted-foreground">
              your agent's personality lives in knowledge. talk to them and they'll evolve — or edit entries below.
            </p>
            {agentDirty && (
              <Button onClick={saveAgent} disabled={saving} size="sm" className="self-end">
                <Save className="h-3.5 w-3.5 mr-1" />
                {saving ? 'saving...' : 'save'}
              </Button>
            )}
          </div>
        </section>

        {/* Knowledge — soul/identity first, then everything else */}
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
            <Brain className="h-3.5 w-3.5" /> knowledge
          </h2>

          {soulEntries.length > 0 && (
            <div className="bg-primary/5 border border-primary/15 rounded-lg overflow-hidden mb-3">
              <div className="px-3 py-2 flex items-center gap-1.5 border-b border-primary/10">
                <Pin className="h-3 w-3 text-primary" />
                <span className="text-[10px] font-semibold uppercase tracking-wider text-primary/70">
                  identity — always in {agentName}'s context
                </span>
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

          {otherEntries.length > 0 && (
            <div className="bg-card border rounded-lg overflow-hidden divide-y">
              {otherEntries.map(k => (
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
            <p className="text-sm text-muted-foreground">
              {agentName} will build up knowledge as you talk. ask it to remember things, or it'll learn on its own.
            </p>
          )}
        </section>

        {/* Skills */}
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">skills</h2>
          {skills.length > 0 ? (
            <div className="bg-card border rounded-lg divide-y">
              {skills.map(s => (
                <div key={s.name} className="px-4 py-3">
                  <span className="text-sm font-medium">{s.name}</span>
                  <p className="text-xs text-muted-foreground mt-0.5">{s.description}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">no skills configured yet</p>
          )}
        </section>

        {/* API Keys */}
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
            <Key className="h-3.5 w-3.5" /> API keys
          </h2>
          {data.api_keys.length > 0 && (
            <div className="bg-card border rounded-lg mb-3 divide-y">
              {data.api_keys.map(key => (
                <div key={key.id} className="flex items-center justify-between px-4 py-3 gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-medium text-sm truncate">{key.name}</span>
                    <code className="text-xs text-muted-foreground shrink-0">{key.key_prefix}...</code>
                  </div>
                  <Button variant="ghost" size="sm" className="shrink-0" onClick={() => deleteApiKey(key.id)}>revoke</Button>
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
            <Input placeholder="key name" value={keyName} onChange={e => setKeyName(e.target.value)} className="flex-1 sm:max-w-xs" />
            <Button type="submit" variant="secondary" size="sm" className="shrink-0">create key</Button>
          </form>
        </section>
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
        {expanded
          ? <ChevronDown className={cn('h-3 w-3 shrink-0', entry.pinned ? 'text-primary/60' : 'text-muted-foreground')} />
          : <ChevronRight className={cn('h-3 w-3 shrink-0', entry.pinned ? 'text-primary/60' : 'text-muted-foreground')} />
        }
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
