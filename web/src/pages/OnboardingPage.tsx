import { useState } from 'react'
import { fetchJSON } from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export default function OnboardingPage({ onSuccess }: { onSuccess: () => void }) {
  const [step, setStep] = useState(1)
  const [name, setName] = useState('')
  const [agentName, setAgentName] = useState('')
  const [error, setError] = useState('')

  async function submitStep1(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!name.trim()) { setError('please enter your name'); return }
    setStep(2)
  }

  async function submitStep2(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!agentName.trim()) { setError('give your agent a name'); return }

    try {
      await fetchJSON('/onboarding', {
        method: 'POST',
        body: JSON.stringify({
          display_name: name.trim(),
          agent_name: agentName.trim(),
        }),
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

        {step === 1 ? (
          <>
            <p className="text-sm text-muted-foreground">hey there! before we dive in&hellip;</p>
            <form onSubmit={submitStep1} className="flex flex-col gap-3">
              <label className="text-sm font-medium text-foreground" htmlFor="name-input">
                what should I call you?
              </label>
              <Input
                type="text"
                id="name-input"
                placeholder="your name"
                autoFocus
                value={name}
                onChange={e => setName(e.target.value)}
              />
              <Button type="submit" className="w-full">next</Button>
            </form>
          </>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              nice to meet you, {name}! name your personal agent &mdash; they'll learn who they are as you talk to them.
            </p>
            <form onSubmit={submitStep2} className="flex flex-col gap-3">
              <label className="text-sm font-medium text-foreground" htmlFor="agent-name">
                agent name
              </label>
              <Input
                type="text"
                id="agent-name"
                placeholder="e.g. Maya, Atlas, Sage..."
                autoFocus
                value={agentName}
                onChange={e => setAgentName(e.target.value)}
              />
              <Button type="submit" className="w-full">let's go</Button>
            </form>
          </>
        )}

        <p className="text-xs text-muted-foreground text-center">
          {step === 1 ? 'crow remembers who you are and what you care about' : 'your agent builds their personality through conversation'}
        </p>

        {error && <p className="text-sm text-destructive text-center">{error}</p>}
      </div>
    </div>
  )
}
