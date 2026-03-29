import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Job } from '../../api'
import { fetchJSON } from '../../api'
import { Circle, CircleCheck, CircleX, Clock, Square } from 'lucide-react'
import { cn } from '@/lib/utils'

function Elapsed({ since }: { since: string }) {
  const [, tick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => tick(n => n + 1), 1000)
    return () => clearInterval(id)
  }, [])
  const s = Math.floor((Date.now() - new Date(since).getTime()) / 1000)
  if (s < 60) return <span>{s}s</span>
  if (s < 3600) return <span>{Math.floor(s / 60)}m {s % 60}s</span>
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h < 24) return <span>{h}h {m}m</span>
  const d = Math.floor(h / 24)
  return <span>{d}d {h % 24}h</span>
}

function formatDuration(startedAt: string, completedAt: string): string {
  const s = Math.floor((new Date(completedAt).getTime() - new Date(startedAt).getTime()) / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  const h = Math.floor(s / 3600)
  return `${h}h ${Math.floor((s % 3600) / 60)}m`
}

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

const statusIcon: Record<string, React.ReactNode> = {
  pending: <Clock className="h-3 w-3 text-muted-foreground" />,
  running: <Circle className="h-3 w-3 text-green-500 fill-green-500" />,
  completed: <CircleCheck className="h-3 w-3 text-muted-foreground" />,
  failed: <CircleX className="h-3 w-3 text-destructive" />,
}

interface JobWithProgress extends Job {
  _progress?: string
}

export default function JobList({ jobs }: { jobs: JobWithProgress[] }) {
  const navigate = useNavigate()

  const sorted = [...jobs].sort((a, b) => {
    const active = (s: string) => s === 'running' || s === 'pending' ? 0 : 1
    const diff = active(a.status) - active(b.status)
    if (diff !== 0) return diff
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })

  if (sorted.length === 0) {
    return <p className="text-sm text-muted-foreground px-3 py-4">no jobs yet</p>
  }

  async function cancelJob(e: React.MouseEvent, jobId: string) {
    e.stopPropagation()
    await fetchJSON(`/jobs/${jobId}/cancel`, { method: 'POST' })
  }

  return (
    <div className="flex flex-col">
      {sorted.map(job => {
        const isRunning = job.status === 'running' || job.status === 'pending'
        const isBg = job.mode === 'background'
        return (
          <div
            key={job.id}
            className={cn(
              'px-3 py-2 border-b last:border-0 transition-colors',
              job.conversation_id ? 'cursor-pointer hover:bg-sidebar-accent/30' : '',
              isRunning && !isBg && 'border-l-2 border-l-green-500',
              isRunning && isBg && 'border-l-2 border-l-primary',
            )}
            onClick={() => job.conversation_id && navigate(`/chat/${job.conversation_id}`)}
          >
            <div className="flex items-center gap-2">
              {statusIcon[job.status]}
              <Badge variant="outline" className="text-xs">{job.agent_name}</Badge>
              {isBg && (
                <Badge variant="secondary" className="text-[10px] px-1 py-0">bg</Badge>
              )}
              <span className="flex-1" />
              {isRunning && (
                <>
                  {job.started_at && (
                    <span className="text-xs text-muted-foreground tabular-nums">
                      <Elapsed since={job.started_at} />
                    </span>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5 text-muted-foreground hover:text-destructive"
                    onClick={(e) => cancelJob(e, job.id)}
                    title="Stop job"
                  >
                    <Square className="h-3 w-3" />
                  </Button>
                </>
              )}
              {job.status === 'completed' && (
                <span
                  className="text-xs text-muted-foreground"
                  title={job.completed_at ? new Date(job.completed_at).toLocaleString() : undefined}
                >
                  {job.started_at && job.completed_at
                    ? `${formatDuration(job.started_at, job.completed_at)} · ${timeAgo(job.completed_at)}`
                    : 'done'
                  }
                </span>
              )}
              {job.status === 'failed' && (
                <span className="text-xs text-destructive">failed</span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1 truncate">
              {isRunning && job._progress ? job._progress : job.input}
            </p>
            {job.error && (
              <p className="text-xs text-destructive mt-0.5 truncate">{job.error}</p>
            )}
          </div>
        )
      })}
    </div>
  )
}
