import { useState } from 'react'
import { fetchJSON } from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export default function OnboardingPage({ onSuccess }: { onSuccess: () => void }) {
  const [name, setName] = useState('')
  const [error, setError] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!name.trim()) { setError('please enter your name'); return }

    try {
      await fetchJSON('/onboarding', {
        method: 'POST',
        body: JSON.stringify({ display_name: name.trim() }),
      })
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-purple-950 via-purple-800 to-purple-600 p-4">
      <div className="bg-card rounded-2xl border border-white/10 p-8 w-full max-w-sm shadow-2xl flex flex-col gap-4">
        <h1 className="text-3xl font-bold text-primary tracking-tight">crow</h1>
        <p className="text-sm text-muted-foreground">hey there! before we dive in&hellip;</p>

        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="text-sm font-medium text-foreground" htmlFor="name-input">what should I call you?</label>
          <Input
            type="text"
            id="name-input"
            placeholder="your name"
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
          />
          <Button type="submit" className="w-full">let's go</Button>
        </form>
        <p className="text-xs text-muted-foreground text-center">crow remembers who you are and what you care about</p>

        {error && <p className="text-sm text-destructive text-center">{error}</p>}
      </div>
    </div>
  )
}
