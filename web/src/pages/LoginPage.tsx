import { useRef, useState } from 'react'
import { fetchJSON } from '../api'

export default function LoginPage({ onSuccess }: { onSuccess: () => void }) {
  const [step, setStep] = useState<'email' | 'code'>('email')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [digits, setDigits] = useState(['', '', '', '', '', ''])
  const digitRefs = useRef<(HTMLInputElement | null)[]>([])

  async function sendCode(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!email.trim()) { setError('please enter your email'); return }

    setStatus('sending code...')
    try {
      await fetchJSON('/auth/send-code', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim() }),
      })
      setStatus('')
      setStep('code')
      setTimeout(() => digitRefs.current[0]?.focus(), 50)
    } catch (err) {
      setStatus('')
      setError(err instanceof Error ? err.message : 'failed to send code')
    }
  }

  async function verify(code?: string) {
    setError('')
    const otp = code ?? digits.join('')
    if (otp.length !== 6) { setError('please enter the full 6-digit code'); return }

    try {
      await fetchJSON('/auth/verify', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim(), code: otp }),
      })
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'verification failed')
    }
  }

  function handleDigitInput(idx: number, value: string) {
    const next = [...digits]
    next[idx] = value.slice(-1)
    setDigits(next)
    if (value && idx < 5) digitRefs.current[idx + 1]?.focus()
  }

  function handleDigitKeyDown(idx: number, e: React.KeyboardEvent) {
    if (e.key === 'Backspace' && !digits[idx] && idx > 0) {
      const next = [...digits]
      next[idx - 1] = ''
      setDigits(next)
      digitRefs.current[idx - 1]?.focus()
    }
  }

  function handlePaste(e: React.ClipboardEvent) {
    e.preventDefault()
    const text = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    const next = [...digits]
    for (let i = 0; i < 6; i++) next[i] = text[i] || ''
    setDigits(next)
    if (text.length === 6) {
      digitRefs.current[5]?.focus()
      verify(text)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-logo">crow</h1>
        <p className="auth-subtitle">sign in to continue</p>

        {step === 'email' ? (
          <form onSubmit={sendCode}>
            <input
              type="email"
              className="input"
              placeholder="your email"
              autoComplete="email"
              autoFocus
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
            <button type="submit" className="btn btn-primary">send code</button>
          </form>
        ) : (
          <form onSubmit={e => { e.preventDefault(); verify() }}>
            <p className="code-label">
              enter the 6-digit code sent to <span>{email}</span>
            </p>
            <div className="otp-inputs">
              {digits.map((d, i) => (
                <input
                  key={i}
                  ref={el => { digitRefs.current[i] = el }}
                  type="text"
                  maxLength={1}
                  inputMode="numeric"
                  className="otp-digit"
                  value={d}
                  onChange={e => handleDigitInput(i, e.target.value)}
                  onKeyDown={e => handleDigitKeyDown(i, e)}
                  onPaste={handlePaste}
                />
              ))}
            </div>
            <button type="submit" className="btn btn-primary">verify</button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => { setStep('email'); setDigits(['', '', '', '', '', '']); setError('') }}
            >
              use a different email
            </button>
          </form>
        )}

        {error && <p className="error">{error}</p>}
        {status && <p className="status">{status}</p>}
      </div>
    </div>
  )
}
