import type { Worker } from '../../api'
import { Circle } from 'lucide-react'

function timeSince(iso: string) {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m ago`
}

export default function WorkerList({ workers }: { workers: Worker[] }) {
  if (workers.length === 0) {
    return <p className="text-sm text-muted-foreground px-3 py-4">no workers registered</p>
  }

  return (
    <div className="flex flex-col">
      {workers.map(w => {
        const online = (Date.now() - new Date(w.last_heartbeat).getTime()) < 60_000
        return (
          <div key={w.id} className="px-3 py-2 border-b last:border-0 flex items-center gap-2">
            <Circle className={`h-3 w-3 ${online ? 'text-green-500 fill-green-500' : 'text-muted-foreground'}`} />
            <div className="flex-1 min-w-0">
              <p className="text-sm truncate">{w.name || w.id.slice(0, 8)}</p>
              <p className="text-xs text-muted-foreground">
                {online ? 'online' : 'offline'} &middot; {timeSince(w.last_heartbeat)}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
