import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type { ScheduledJob } from '../../api'
import { Trash2 } from 'lucide-react'

function relativeTime(iso: string) {
  const diff = new Date(iso).getTime() - Date.now()
  if (diff < 0) return 'overdue'
  const s = Math.floor(diff / 1000)
  if (s < 60) return `in ${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `in ${m}m`
  const h = Math.floor(m / 60)
  return `in ${h}h ${m % 60}m`
}

export default function ScheduledJobList({
  scheduledJobs,
  onCancel,
}: {
  scheduledJobs: ScheduledJob[]
  onCancel: (id: string) => void
}) {
  const active = scheduledJobs.filter(s => s.status === 'active')

  if (active.length === 0) {
    return <p className="text-sm text-muted-foreground px-3 py-4">no scheduled jobs</p>
  }

  return (
    <div className="flex flex-col">
      {active.map(sj => (
        <div key={sj.id} className="px-3 py-2 border-b last:border-0">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">{sj.agent_name}</Badge>
            <span className="flex-1" />
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => onCancel(sj.id)}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-1 truncate">{sj.input}</p>
          <div className="flex gap-2 mt-1 text-xs text-muted-foreground">
            {sj.cron && <span>cron: {sj.cron}</span>}
            <span>next: {relativeTime(sj.run_at)}</span>
          </div>
        </div>
      ))}
    </div>
  )
}
