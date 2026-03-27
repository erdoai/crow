import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import type { Job, JobEvent } from '../../api'
import { Circle, CircleCheck, CircleX, Clock, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import JobDetail from './JobDetail'

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

type JobWithMeta = Job & { _progress?: string; _events?: JobEvent[] }

export default function JobList({ jobs }: { jobs: JobWithMeta[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const navigate = useNavigate()

  // Pin active jobs to top, then recent by time
  const sorted = [...jobs].sort((a, b) => {
    const active = (s: string) => s === 'running' || s === 'pending' ? 0 : 1
    const diff = active(a.status) - active(b.status)
    if (diff !== 0) return diff
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })

  if (sorted.length === 0) {
    return <p className="text-sm text-muted-foreground px-3 py-4">no jobs yet</p>
  }

  return (
    <div className="flex flex-col">
      {sorted.map(job => {
        const isExpanded = expandedId === job.id
        const hasConversation = !!job.conversation_id
        return (
          <div key={job.id} className="border-b last:border-0">
            <div
              className={cn(
                'px-3 py-2 cursor-pointer transition-colors',
                isExpanded ? 'bg-sidebar-accent/50' : 'hover:bg-sidebar-accent/30',
                (job.status === 'running') && 'border-l-2 border-l-green-500',
              )}
              onClick={() => setExpandedId(isExpanded ? null : job.id)}
            >
              <div className="flex items-center gap-2">
                {statusIcon[job.status]}
                <Badge variant="outline" className="text-xs">{job.agent_name}</Badge>
                {job.mode === 'background' && (
                  <Badge variant="secondary" className="text-[10px] px-1 py-0">bg</Badge>
                )}
                <span className="flex-1" />
                {job.status === 'running' && job.started_at && (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    <Elapsed since={job.started_at} />
                  </span>
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
              <p className="text-xs text-muted-foreground mt-1 truncate">{job.input}</p>
              {!isExpanded && job._progress && (
                <p className="text-xs text-primary mt-1 truncate">{job._progress}</p>
              )}
              {!isExpanded && job.error && (
                <p className="text-xs text-destructive mt-1 truncate">{job.error}</p>
              )}
            </div>
            {/* Expanded detail */}
            <div
              className={cn(
                'grid transition-all duration-200 ease-in-out',
                isExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
              )}
            >
              <div className="overflow-hidden bg-sidebar-accent/20">
                {isExpanded && (
                  <>
                    <JobDetail events={job._events || []} output={job.output} status={job.status} />
                    {hasConversation && (
                      <button
                        className="w-full px-3 py-1.5 text-[10px] text-primary hover:underline flex items-center gap-1 border-t border-border/50"
                        onClick={(e) => {
                          e.stopPropagation()
                          navigate(`/chat/${job.conversation_id}`)
                        }}
                      >
                        <MessageSquare className="h-2.5 w-2.5" />
                        open conversation
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
