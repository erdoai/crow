import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { Job, ScheduledJob, Worker } from '../../api'
import { Circle, CircleCheck, CircleX, Clock, ChevronDown, ChevronRight, Calendar, Radio } from 'lucide-react'
import { cn } from '@/lib/utils'
import JobList from './JobList'

interface Props {
  jobs: Job[]
  scheduledJobs: ScheduledJob[]
  workers: Worker[]
  cancelScheduledJob: (id: string) => Promise<void>
}

export default function ActivitySection({ jobs, scheduledJobs, workers }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [showAll, setShowAll] = useState(false)

  const runningCount = jobs.filter(j => j.status === 'running' || j.status === 'pending').length
  const activeScheduled = scheduledJobs.filter(s => s.status === 'active').length
  const onlineWorkers = workers.filter(w =>
    (Date.now() - new Date(w.last_heartbeat).getTime()) < 60_000
  ).length

  // Default: only active + recent background jobs. Toggle to show all.
  const filteredJobs = showAll
    ? jobs
    : jobs.filter(j => j.source !== 'message' || j.status === 'running' || j.status === 'pending')
  const displayJobs = filteredJobs.slice(0, showAll ? 50 : 8)

  return (
    <div className="flex flex-col">
      <button
        className="px-3 py-2 flex items-center gap-1.5 hover:bg-sidebar-accent/50 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        {expanded
          ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
          : <ChevronRight className="h-3 w-3 text-muted-foreground" />
        }
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">activity</span>
        {runningCount > 0 && (
          <Badge variant="default" className="ml-auto h-4 px-1.5 text-[10px] font-medium animate-pulse">
            {runningCount}
          </Badge>
        )}
      </button>

      {expanded && (
        <div className="flex flex-col">
          {/* Summary badges */}
          <div className="px-3 pb-1.5 flex items-center gap-2 text-[10px] text-muted-foreground">
            {activeScheduled > 0 && (
              <span className="flex items-center gap-0.5">
                <Calendar className="h-2.5 w-2.5" />
                {activeScheduled} scheduled
              </span>
            )}
            {onlineWorkers > 0 && (
              <span className="flex items-center gap-0.5">
                <Radio className="h-2.5 w-2.5 text-green-500" />
                {onlineWorkers} online
              </span>
            )}
          </div>

          {/* Jobs list */}
          <ScrollArea className="max-h-64">
            <JobList jobs={displayJobs} />
          </ScrollArea>

          {/* Footer controls */}
          <div className="px-3 py-1.5 flex items-center gap-2">
            <button
              className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => setShowAll(a => !a)}
            >
              {showAll ? 'hide chat jobs' : 'show all'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
