import { useEffect, useRef } from 'react'
import { toast } from 'sonner'
import type { Job } from '../api'

/**
 * Shows toast and browser notifications when jobs complete or fail.
 * Skips notifications for jobs in the currently viewed conversation.
 */
export function useJobNotifications(
  jobs: Job[],
  currentConversationId: string | null,
) {
  const prevStatusRef = useRef<Map<string, string>>(new Map())
  const tabVisibleRef = useRef(true)

  // Track tab visibility for browser notifications
  useEffect(() => {
    const handler = () => {
      tabVisibleRef.current = document.visibilityState === 'visible'
    }
    document.addEventListener('visibilitychange', handler)
    return () => document.removeEventListener('visibilitychange', handler)
  }, [])

  // Request browser notification permission on mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
  }, [])

  useEffect(() => {
    const prev = prevStatusRef.current

    for (const job of jobs) {
      const oldStatus = prev.get(job.id)
      if (!oldStatus) {
        // First time seeing this job — record status, don't notify
        prev.set(job.id, job.status)
        continue
      }

      if (oldStatus === job.status) continue
      prev.set(job.id, job.status)

      // Don't notify for chat jobs in the current conversation (user sees the response)
      // Always notify for background jobs
      const isBg = 'mode' in job && (job as Job & { mode?: string }).mode === 'background'
      if (!isBg && job.source === 'message' && currentConversationId) continue

      if (job.status === 'completed') {
        toast.success(`${job.agent_name} completed`, {
          description: job.input.slice(0, 80),
        })
        sendBrowserNotification(
          `${job.agent_name} completed`,
          job.input.slice(0, 100),
        )
      } else if (job.status === 'failed') {
        toast.error(`${job.agent_name} failed`, {
          description: job.error?.slice(0, 80) || job.input.slice(0, 80),
        })
        sendBrowserNotification(
          `${job.agent_name} failed`,
          job.error?.slice(0, 100) || job.input.slice(0, 100),
        )
      }
    }

    // Clean up old entries for jobs no longer in the list
    const currentIds = new Set(jobs.map(j => j.id))
    for (const id of prev.keys()) {
      if (!currentIds.has(id)) prev.delete(id)
    }
  }, [jobs, currentConversationId])
}

function sendBrowserNotification(title: string, body: string) {
  if (
    'Notification' in window &&
    Notification.permission === 'granted' &&
    document.visibilityState === 'hidden'
  ) {
    const n = new Notification(title, { body, icon: '/favicon.ico' })
    n.onclick = () => {
      window.focus()
      n.close()
    }
  }
}
