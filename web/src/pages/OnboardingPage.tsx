import { useState } from 'react'
import { fetchJSON } from '../api'

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
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-logo">crow</h1>
        <p className="auth-subtitle">welcome! one quick thing&hellip;</p>

        <form onSubmit={submit}>
          <label className="input-label" htmlFor="name-input">what should I call you?</label>
          <input
            type="text"
            id="name-input"
            className="input"
            placeholder="your name"
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
          />
          <button type="submit" className="btn btn-primary">get started</button>
        </form>

        {error && <p className="error">{error}</p>}
      </div>
    </div>
  )
}
