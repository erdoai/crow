import { useCallback, useEffect, useReducer, useRef } from 'react'
import { fetchJSON, type Job, type ScheduledJob, type Worker } from '../api'

interface State {
  jobs: Job[]
  scheduledJobs: ScheduledJob[]
  workers: Worker[]
}

type Action =
  | { type: 'INIT_JOBS'; jobs: Job[] }
  | { type: 'INIT_SCHEDULED'; scheduledJobs: ScheduledJob[] }
  | { type: 'INIT_WORKERS'; workers: Worker[] }
  | { type: 'JOB_STARTED'; data: { job_id: string; agent_name: string; input?: string } }
  | { type: 'JOB_COMPLETED'; data: { job_id: string } }
  | { type: 'JOB_FAILED'; data: { job_id: string; error?: string } }
  | { type: 'JOB_PROGRESS'; data: { job_id: string; status: string } }
  | { type: 'REMOVE_SCHEDULED'; id: string }

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
      const newJob: Job = {
        id: action.data.job_id,
        agent_name: action.data.agent_name,
        status: 'running',
        input: action.data.input || '',
        output: null,
        worker_id: null,
        error: null,
        created_at: new Date().toISOString(),
        started_at: new Date().toISOString(),
        completed_at: null,
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
            ? { ...j, status: 'failed' as const, error: action.data.error || null, completed_at: new Date().toISOString() }
            : j
        ),
      }
    case 'JOB_PROGRESS':
      return {
        ...state,
        jobs: state.jobs.map(j =>
          j.id === action.data.job_id
            ? { ...j, _progress: action.data.status } as Job
            : j
        ),
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
  const sseRef = useRef<EventSource | null>(null)

  // Initial data load
  useEffect(() => {
    if (!enabled) return
    fetchJSON<Job[]>('/jobs?limit=20').then(jobs => dispatch({ type: 'INIT_JOBS', jobs }))
    fetchJSON<ScheduledJob[]>('/scheduled-jobs').then(scheduledJobs => dispatch({ type: 'INIT_SCHEDULED', scheduledJobs }))
    fetchJSON<Worker[]>('/workers').then(workers => dispatch({ type: 'INIT_WORKERS', workers }))
  }, [enabled])

  // SSE for real-time updates
  useEffect(() => {
    if (!enabled) {
      sseRef.current?.close()
      sseRef.current = null
      return
    }

    const source = new EventSource('/api/state/stream')
    sseRef.current = source

    source.addEventListener('job.started', (e) => {
      const { data } = JSON.parse(e.data)
      dispatch({ type: 'JOB_STARTED', data })
    })
    source.addEventListener('job.completed', (e) => {
      const { data } = JSON.parse(e.data)
      dispatch({ type: 'JOB_COMPLETED', data })
    })
    source.addEventListener('job.failed', (e) => {
      const { data } = JSON.parse(e.data)
      dispatch({ type: 'JOB_FAILED', data })
    })
    source.addEventListener('job.progress', (e) => {
      const { data } = JSON.parse(e.data)
      dispatch({ type: 'JOB_PROGRESS', data })
    })

    return () => {
      source.close()
      sseRef.current = null
    }
  }, [enabled])

  // Refresh workers periodically (no SSE events for heartbeats)
  useEffect(() => {
    if (!enabled) return
    const id = setInterval(() => {
      fetchJSON<Worker[]>('/workers').then(workers => dispatch({ type: 'INIT_WORKERS', workers }))
    }, 30_000)
    return () => clearInterval(id)
  }, [enabled])

  const cancelScheduledJob = useCallback(async (id: string) => {
    await fetchJSON(`/scheduled-jobs/${id}`, { method: 'DELETE' })
    dispatch({ type: 'REMOVE_SCHEDULED', id })
  }, [])

  return { ...state, cancelScheduledJob }
}
