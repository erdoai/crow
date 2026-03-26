import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import type { Job } from '../../api'
import { Circle, CircleX, Clock } from 'lucide-react'

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
  failed: <CircleX className="h-3 w-3 text-destructive" />,
}

export default function JobList({ jobs }: { jobs: Job[] }) {
  // Only show active jobs + recent failures — completed jobs are just chat noise
  const active = jobs.filter(j => j.status === 'running' || j.status === 'pending')
  const failed = jobs.filter(j => j.status === 'failed').slice(0, 3)
  const sorted = [...active, ...failed].sort((a, b) => {
    const order = { running: 0, pending: 1, failed: 2, completed: 3 }
    const diff = order[a.status] - order[b.status]
    if (diff !== 0) return diff
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })

  if (sorted.length === 0) {
    return <p className="text-sm text-muted-foreground px-3 py-4">nothing running</p>
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
