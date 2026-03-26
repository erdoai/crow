import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useActivityStream } from '../../hooks/useActivityStream'
import JobList from './JobList'
import ScheduledJobList from './ScheduledJobList'
import WorkerList from './WorkerList'

type Tab = 'jobs' | 'scheduled' | 'workers'

export default function ActivityPanel({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>('jobs')
  const [showAll, setShowAll] = useState(false)
  const { jobs, scheduledJobs, workers, cancelScheduledJob } = useActivityStream(true)

  // Default: only background jobs (schedule). Toggle to show all including chat messages.
  const filteredJobs = showAll ? jobs : jobs.filter(j =>
    j.source !== 'message' || j.status === 'running' || j.status === 'pending'
  )

  return (
    <aside className="w-80 min-w-80 border-l flex flex-col bg-sidebar">
      <div className="p-4 flex items-center justify-between border-b border-sidebar-border">
        <span className="text-sm font-semibold">activity</span>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex border-b border-sidebar-border">
        {(['jobs', 'scheduled', 'workers'] as Tab[]).map(t => (
          <button
            key={t}
            className={cn(
              'flex-1 px-3 py-2 text-xs font-medium transition-colors',
              tab === t
                ? 'border-b-2 border-primary text-primary'
                : 'text-muted-foreground hover:text-foreground'
            )}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      <ScrollArea className="flex-1">
        {tab === 'jobs' && (
          <>
            <div className="px-3 pt-2 pb-1">
              <button
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setShowAll(a => !a)}
              >
                {showAll ? 'hide chat jobs' : 'show all jobs'}
              </button>
            </div>
            <JobList jobs={filteredJobs} />
          </>
        )}
        {tab === 'scheduled' && (
          <ScheduledJobList scheduledJobs={scheduledJobs} onCancel={cancelScheduledJob} />
        )}
        {tab === 'workers' && <WorkerList workers={workers} />}
      </ScrollArea>
    </aside>
  )
}
