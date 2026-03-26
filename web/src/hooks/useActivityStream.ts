import { useCallback, useEffect, useReducer } from 'react'
import { fetchJSON, type Job, type JobEvent, type ScheduledJob, type Worker } from '../api'
import { useWebSocket } from './useWebSocket'

const MAX_EVENTS_PER_JOB = 100

interface JobWithEvents extends Job {
  _progress?: string
  _events?: JobEvent[]
}

interface State {
  jobs: JobWithEvents[]
  scheduledJobs: ScheduledJob[]
  workers: Worker[]
}

type Action =
  | { type: 'INIT_JOBS'; jobs: Job[] }
  | { type: 'INIT_SCHEDULED'; scheduledJobs: ScheduledJob[] }
  | { type: 'INIT_WORKERS'; workers: Worker[] }
  | { type: 'JOB_STARTED'; data: { job_id: string; agent_name: string; input?: string; source?: string; mode?: string } }
  | { type: 'JOB_COMPLETED'; data: { job_id: string } }
  | { type: 'JOB_FAILED'; data: { job_id: string; error?: string } }
  | { type: 'JOB_PROGRESS'; data: { job_id: string; status: string; agent_name?: string } }
  | { type: 'MESSAGE_CHUNK'; data: { job_id: string; type: string; text?: string; tool_name?: string; agent_name?: string } }
  | { type: 'REMOVE_SCHEDULED'; id: string }

function pushEvent(job: JobWithEvents, event: JobEvent): JobEvent[] {
  const events = [...(job._events || []), event]
  return events.length > MAX_EVENTS_PER_JOB ? events.slice(-MAX_EVENTS_PER_JOB) : events
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'INIT_JOBS':
      return { ...state, jobs: action.jobs }
    case 'INIT_SCHEDULED':
      return { ...state, scheduledJobs: action.scheduledJobs }
    case 'INIT_WORKERS':
      return { ...state, workers: action.workers }
    case 'JOB_STARTED': {
      const exists = state.jobs.some(j => j.id === action.data.job_id)
      if (exists) {
        return {
          ...state,
          jobs: state.jobs.map(j =>
            j.id === action.data.job_id
              ? { ...j, status: 'running' as const, started_at: new Date().toISOString() }
              : j
          ),
        }
      }
      const newJob: JobWithEvents = {
        id: action.data.job_id,
        agent_name: action.data.agent_name,
        status: 'running',
        source: (action.data.source as Job['source']) || 'message',
        mode: (action.data.mode as Job['mode']) || 'chat',
        input: action.data.input || '',
        output: null,
        worker_id: null,
        error: null,
        created_at: new Date().toISOString(),
        started_at: new Date().toISOString(),
        completed_at: null,
        _events: [],
      }
      return { ...state, jobs: [newJob, ...state.jobs] }
    }
    case 'JOB_COMPLETED':
      return {
        ...state,
        jobs: state.jobs.map(j =>
          j.id === action.data.job_id
            ? { ...j, status: 'completed' as const, completed_at: new Date().toISOString() }
            : j
        ),
      }
    case 'JOB_FAILED':
      return {
        ...state,
        jobs: state.jobs.map(j =>
          j.id === action.data.job_id
            ? {
                ...j,
                status: 'failed' as const,
                error: action.data.error || null,
                completed_at: new Date().toISOString(),
                _events: pushEvent(j, {
                  type: 'error',
                  text: action.data.error,
                  timestamp: new Date().toISOString(),
                }),
              }
            : j
        ),
      }
    case 'JOB_PROGRESS':
      return {
        ...state,
        jobs: state.jobs.map(j =>
          j.id === action.data.job_id
            ? {
                ...j,
                _progress: action.data.status,
                _events: pushEvent(j, {
                  type: 'progress',
                  text: action.data.status,
                  agent_name: action.data.agent_name,
                  timestamp: new Date().toISOString(),
                }),
              }
            : j
        ),
      }
    case 'MESSAGE_CHUNK': {
      const { job_id, type, text, tool_name, agent_name } = action.data
      let eventType: JobEvent['type']
      if (type === 'tool_call') eventType = 'tool_call'
      else if (type === 'tool_result') eventType = 'tool_result'
      else eventType = 'text'

      return {
        ...state,
        jobs: state.jobs.map(j =>
          j.id === job_id
            ? {
                ...j,
                _events: pushEvent(j, {
                  type: eventType,
                  text: text ?? undefined,
                  tool_name: tool_name ?? undefined,
                  agent_name: agent_name ?? undefined,
                  timestamp: new Date().toISOString(),
                }),
              }
            : j
        ),
      }
    }
    case 'REMOVE_SCHEDULED':
      return {
        ...state,
        scheduledJobs: state.scheduledJobs.filter(s => s.id !== action.id),
      }
    default:
      return state
  }
}

const INITIAL: State = { jobs: [], scheduledJobs: [], workers: [] }

export function useActivityStream(enabled: boolean) {
  const [state, dispatch] = useReducer(reducer, INITIAL)

  // Initial data load
  useEffect(() => {
    if (!enabled) return
    fetchJSON<Job[]>('/jobs?limit=50').then(jobs =>
      dispatch({ type: 'INIT_JOBS', jobs }),
    )
    fetchJSON<ScheduledJob[]>('/scheduled-jobs').then(scheduledJobs =>
      dispatch({ type: 'INIT_SCHEDULED', scheduledJobs }),
    )
    fetchJSON<Worker[]>('/workers').then(workers =>
      dispatch({ type: 'INIT_WORKERS', workers }),
    )
  }, [enabled])

  // WebSocket for real-time updates (replaces SSE)
  const onEvent = useCallback(
    (event: { type: string; data: Record<string, unknown> }) => {
      const { data } = event
      switch (event.type) {
        case 'job.started':
          dispatch({ type: 'JOB_STARTED', data: data as Action & { type: 'JOB_STARTED' } extends { data: infer D } ? D : never })
          break
        case 'job.completed':
          dispatch({ type: 'JOB_COMPLETED', data: data as { job_id: string } })
          break
        case 'job.failed':
          dispatch({ type: 'JOB_FAILED', data: data as { job_id: string; error?: string } })
          break
        case 'job.progress':
          dispatch({ type: 'JOB_PROGRESS', data: data as { job_id: string; status: string } })
          break
        case 'message.chunk':
          if (data.job_id) {
            dispatch({ type: 'MESSAGE_CHUNK', data: data as { job_id: string; type: string; text?: string; tool_name?: string; agent_name?: string } })
          }
          break
      }
    },
    [],
  )

  useWebSocket({ onEvent, enabled })

  // Refresh workers periodically (no events for heartbeats)
  useEffect(() => {
    if (!enabled) return
    const id = setInterval(() => {
      fetchJSON<Worker[]>('/workers').then(workers =>
        dispatch({ type: 'INIT_WORKERS', workers }),
      )
    }, 30_000)
    return () => clearInterval(id)
  }, [enabled])

  const cancelScheduledJob = useCallback(async (id: string) => {
    await fetchJSON(`/scheduled-jobs/${id}`, { method: 'DELETE' })
    dispatch({ type: 'REMOVE_SCHEDULED', id })
  }, [])

  return { ...state, cancelScheduledJob }
}
