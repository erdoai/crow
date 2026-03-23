import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchJSON } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Download, Copy, Check, Cpu } from 'lucide-react'

interface SharedAgent {
  name: string
  description: string
  tools: string[]
  mcp_servers: string[]
  knowledge_areas: string[]
}

export default function SharedAgentPage() {
  const { token } = useParams<{ token: string }>()
  const [agent, setAgent] = useState<SharedAgent | null>(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!token) return
    fetchJSON<SharedAgent>(`/api/shared/${token}`)
      .then(setAgent)
      .catch(() => setError('Agent not found or share link expired.'))
  }, [token])

  async function downloadAgent() {
    if (!agent) return
    const res = await fetch(`/agents/${agent.name}/export`)
    if (!res.ok) return
    const text = await res.text()
    const blob = new Blob([text], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${agent.name}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function copyToClipboard() {
    if (!agent) return
    const res = await fetch(`/agents/${agent.name}/export`)
    if (!res.ok) return
    const text = await res.text()
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="text-destructive">not found</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  if (!agent) return null

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-primary text-primary-foreground px-6 py-4">
        <h1 className="text-xl font-bold tracking-tight">crow</h1>
      </header>

      <main className="max-w-xl mx-auto p-6">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 mb-1">
              <Badge variant="secondary" className="text-xs">shared agent</Badge>
            </div>
            <CardTitle className="text-2xl text-primary flex items-center gap-2">
              <Cpu className="h-5 w-5" /> {agent.name}
            </CardTitle>
            <CardDescription className="text-base">{agent.description}</CardDescription>
          </CardHeader>

          <CardContent className="flex flex-col gap-4">
            {agent.tools.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">tools</p>
                <div className="flex flex-wrap gap-1.5">
                  {agent.tools.map(t => <Badge key={t} variant="outline">{t}</Badge>)}
                </div>
              </div>
            )}

            {agent.knowledge_areas.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">knowledge areas</p>
                <div className="flex flex-wrap gap-1.5">
                  {agent.knowledge_areas.map(k => <Badge key={k} variant="outline">{k}</Badge>)}
                </div>
              </div>
            )}

            {agent.mcp_servers.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">MCP servers</p>
                <div className="flex flex-wrap gap-1.5">
                  {agent.mcp_servers.map(m => <Badge key={m} variant="outline">{m}</Badge>)}
                </div>
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <Button onClick={downloadAgent}>
                <Download className="h-4 w-4 mr-1.5" /> download .md
              </Button>
              <Button variant="secondary" onClick={copyToClipboard}>
                {copied
                  ? <><Check className="h-4 w-4 mr-1.5" /> copied</>
                  : <><Copy className="h-4 w-4 mr-1.5" /> copy to clipboard</>
                }
              </Button>
            </div>
          </CardContent>
        </Card>

        <p className="text-xs text-muted-foreground text-center mt-6">
          import this agent into any crow instance via <code className="bg-muted px-1 rounded">POST /agents/import</code>
        </p>
      </main>
    </div>
  )
}
