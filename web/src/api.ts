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
  title: string | null
  updated_at: string | null
}

export type ContentPart = {
  type: string
  text?: string
  name?: string
  id?: string
  input?: Record<string, unknown>
  result?: string
  content?: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string | ContentPart[]
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

export interface DashboardView {
  name: string
  label: string
  url: string
}

export interface DashboardData {
  agents: Agent[]
  conversations: Conversation[]
  knowledge: KnowledgeEntry[]
  api_keys: ApiKey[]
  display_name: string
  auth_enabled: boolean
}

export interface Job {
  id: string
  agent_name: string
  conversation_id: string | null
  status: 'pending' | 'running' | 'completed' | 'failed'
  source: 'message' | 'schedule'
  mode: 'chat' | 'background'
  input: string
  output: string | null
  worker_id: string | null
  error: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  parent_conversation_id: string | null
}

export interface ScheduledJob {
  id: string
  agent_name: string
  input: string
  cron: string | null
  run_at: string
  status: string
  created_at: string
}

export interface Worker {
  id: string
  name: string | null
  last_heartbeat: string
  status: string
}

export interface StoreNamespace {
  namespace: string
  key_count: number
  updated_at: string | null
}

export interface StoreKey {
  key: string
  updated_at: string | null
}

export interface StoreValue {
  namespace: string
  key: string
  data: unknown
}

export interface JobEvent {
  type: 'tool_call' | 'tool_result' | 'text' | 'progress' | 'error'
  text?: string
  tool_name?: string
  agent_name?: string
  timestamp: string
}
