import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import type { Job } from '../../api'
import { Circle, CircleCheck, CircleX, Clock } from 'lucide-react'

function Elapsed({ since }: { since: string }) {
  const [, tick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => tick(n => n + 1), 1000)
    return () => clearInterval(id)
  }, [])
  const s = Math.floor((Date.now() - new Date(since).getTime()) / 1000)
  if (s < 60) return <span>{s}s</span>
  const m = Math.floor(s / 60)
  return <span>{m}m {s % 60}s</span>
}

const statusIcon: Record<string, React.ReactNode> = {
  pending: <Clock className="h-3 w-3 text-muted-foreground" />,
  running: <Circle className="h-3 w-3 text-green-500 fill-green-500" />,
  completed: <CircleCheck className="h-3 w-3 text-muted-foreground" />,
  failed: <CircleX className="h-3 w-3 text-destructive" />,
}

export default function JobList({ jobs }: { jobs: Job[] }) {
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
      {sorted.map(job => (
        <div key={job.id} className="px-3 py-2 border-b last:border-0">
          <div className="flex items-center gap-2">
            {statusIcon[job.status]}
            <Badge variant="outline" className="text-xs">{job.agent_name}</Badge>
            <span className="flex-1" />
            {job.status === 'running' && job.started_at && (
              <span className="text-xs text-muted-foreground tabular-nums">
                <Elapsed since={job.started_at} />
              </span>
            )}
            {job.status === 'completed' && (
              <span className="text-xs text-muted-foreground">done</span>
            )}
            {job.status === 'failed' && (
              <span className="text-xs text-destructive">failed</span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-1 truncate">{job.input}</p>
          {(job as Job & { _progress?: string })._progress && (
            <p className="text-xs text-primary mt-1 truncate">
              {(job as Job & { _progress?: string })._progress}
            </p>
          )}
          {job.error && (
            <p className="text-xs text-destructive mt-1 truncate">{job.error}</p>
          )}
        </div>
      ))}
    </div>
  )
}
