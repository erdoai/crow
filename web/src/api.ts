export class ApiError extends Error {
  status: number
  data: Record<string, unknown>

  constructor(status: number, data: Record<string, unknown>) {
    super((data.detail as string) || `API error ${status}`)
    this.status = status
    this.data = data
  }
}

export async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data)
  }
  return res.json()
}

// Types

export interface User {
  id: string
  email: string
  display_name: string | null
  auth_enabled: boolean
}

export interface Agent {
  name: string
  description: string
}

export interface Conversation {
  id: string
  gateway: string
  gateway_thread_id: string
  updated_at: string | null
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  agent_name: string | null
}

export interface ApiKey {
  id: string
  name: string
  key_prefix: string
}

export interface KnowledgeEntry {
  id: string
  category: string
  title: string
  agent_name: string
}

export interface DashboardData {
  agents: Agent[]
  conversations: Conversation[]
  knowledge: KnowledgeEntry[]
  api_keys: ApiKey[]
  display_name: string
  auth_enabled: boolean
}
