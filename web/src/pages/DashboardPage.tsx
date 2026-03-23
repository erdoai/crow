import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchJSON, type DashboardData } from '../api'

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
    // Refresh dashboard data to show the new key in the list
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
      body: JSON.stringify({ text: "Hi, I'd like to chat with you.", thread_id: threadId, agent: agentName }),
    })
    // Poll for conversation to appear then navigate
    setTimeout(async () => {
      const convs = await fetchJSON<Array<{ id: string; gateway_thread_id: string }>>('/conversations')
      const conv = convs.find(c => c.gateway_thread_id === threadId)
      navigate(conv ? `/chat/${conv.id}` : '/chat')
    }, 1000)
  }

  async function logout() {
    await fetch('/auth/logout', { method: 'POST' })
    window.location.href = '/login'
  }

  if (!data) return null

  return (
    <div className="dashboard">
      <header className="header">
        <div className="header-left">
          <h1 className="header-logo">crow</h1>
        </div>
        <div className="header-right">
          <span className="greeting">hi, {data.display_name}</span>
          {data.auth_enabled && (
            <button className="btn btn-ghost btn-sm" onClick={logout}>sign out</button>
          )}
        </div>
      </header>

      <main className="main">
        {/* Agents */}
        <section className="section">
          <h2 className="section-title">agents</h2>
          <div className="card-grid">
            {data.agents.map(agent => (
              <a
                key={agent.name}
                href="/chat"
                className="card card-link"
                onClick={e => { e.preventDefault(); startChatWithAgent(agent.name) }}
              >
                <h3 className="card-title">{agent.name}</h3>
                <p className="card-desc">{agent.description}</p>
              </a>
            ))}
            {data.agents.length === 0 && <p className="empty">no agents configured</p>}
          </div>
        </section>

        {/* API Keys */}
        <section className="section">
          <h2 className="section-title">API keys</h2>
          {data.api_keys.length > 0 && (
            <div className="list">
              {data.api_keys.map(key => (
                <div key={key.id} className="list-item">
                  <div>
                    <span className="key-name">{key.name}</span>
                    <span className="mono muted">{key.key_prefix}...</span>
                  </div>
                  <button className="btn btn-ghost btn-sm" onClick={() => deleteApiKey(key.id)}>revoke</button>
                </div>
              ))}
            </div>
          )}
          {newKey && (
            <div className="key-result">
              copy this key now (it won't be shown again): {newKey}
            </div>
          )}
          <form className="inline-form" onSubmit={createApiKey}>
            <input
              type="text"
              className="input input-sm"
              placeholder="key name"
              value={keyName}
              onChange={e => setKeyName(e.target.value)}
            />
            <button type="submit" className="btn btn-secondary btn-sm">create key</button>
          </form>
        </section>

        {/* Knowledge */}
        <section className="section">
          <h2 className="section-title">knowledge</h2>
          {data.knowledge.length > 0 ? (
            <div className="list">
              {data.knowledge.map(k => (
                <div key={k.id} className="list-item">
                  <div>
                    <span className="badge">{k.category}</span>
                    <span>{k.title}</span>
                  </div>
                  <span className="muted">{k.agent_name}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty">no knowledge entries yet</p>
          )}
        </section>

        {/* Recent Conversations */}
        <section className="section">
          <h2 className="section-title">recent conversations</h2>
          {data.conversations.length > 0 ? (
            <div className="list">
              {data.conversations.map(c => (
                <a
                  key={c.id}
                  href={`/chat/${c.id}`}
                  className="list-item list-item-link"
                  onClick={e => { e.preventDefault(); navigate(`/chat/${c.id}`) }}
                >
                  <div>
                    <span className="badge">{c.gateway}</span>
                    <span className="mono">{c.gateway_thread_id}</span>
                  </div>
                  <span className="muted">
                    {c.updated_at ? new Date(c.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
                  </span>
                </a>
              ))}
            </div>
          ) : (
            <p className="empty">no conversations yet</p>
          )}
        </section>
      </main>
    </div>
  )
}
