import { ScrollArea } from '@/components/ui/scroll-area'
import type { JobEvent } from '../../api'
import { Wrench, MessageSquare, Activity, AlertCircle, ArrowRight } from 'lucide-react'

interface Props {
  events: JobEvent[]
  output?: string | null
  status?: string
}

function EventIcon({ type }: { type: JobEvent['type'] }) {
  switch (type) {
    case 'tool_call':
      return <Wrench className="h-3 w-3 text-primary shrink-0" />
    case 'tool_result':
      return <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
    case 'text':
      return <MessageSquare className="h-3 w-3 text-muted-foreground shrink-0" />
    case 'progress':
      return <Activity className="h-3 w-3 text-primary shrink-0 animate-pulse" />
    case 'error':
      return <AlertCircle className="h-3 w-3 text-destructive shrink-0" />
  }
}

function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

function EventRow({ event }: { event: JobEvent }) {
  let label: string
  switch (event.type) {
    case 'tool_call':
      label = event.tool_name || 'tool call'
      break
    case 'tool_result':
      label = event.text ? event.text.slice(0, 120) : 'result'
      break
    case 'text':
      label = event.text?.slice(-120) || ''
      break
    case 'progress':
      label = event.text || ''
      break
    case 'error':
      label = event.text || 'error'
      break
  }

  return (
    <div className="flex items-start gap-1.5 py-0.5">
      <EventIcon type={event.type} />
      <span className={`text-[10px] leading-tight truncate flex-1 ${event.type === 'error' ? 'text-destructive' : 'text-muted-foreground'}`}>
        {label}
      </span>
      <span className="text-[9px] text-muted-foreground/50 tabular-nums shrink-0">
        {formatTime(event.timestamp)}
      </span>
    </div>
  )
}

export default function JobDetail({ events, output, status }: Props) {
  const hasEvents = events.length > 0
  const showOutput = status === 'completed' && output

  if (!hasEvents && !showOutput) {
    return (
      <div className="px-3 py-2 text-[10px] text-muted-foreground">
        no events yet...
      </div>
    )
  }

  return (
    <ScrollArea className="max-h-48">
      <div className="px-3 py-1 flex flex-col">
        {events.map((event, i) => (
          <EventRow key={i} event={event} />
        ))}
        {showOutput && (
          <div className="mt-1 pt-1 border-t border-border">
            <p className="text-[10px] text-muted-foreground font-medium mb-0.5">output</p>
            <p className="text-[10px] text-foreground whitespace-pre-wrap break-words">
              {output.slice(0, 500)}
              {output.length > 500 && '...'}
            </p>
          </div>
        )}
      </div>
    </ScrollArea>
  )
}
