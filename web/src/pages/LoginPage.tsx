import { useRef, useState } from 'react'
import { fetchJSON } from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

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
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-purple-950 via-purple-800 to-purple-600 p-4">
      <div className="bg-card rounded-xl p-8 w-full max-w-sm shadow-2xl flex flex-col gap-4">
        <h1 className="text-3xl font-bold text-primary tracking-tight">crow</h1>
        <p className="text-sm text-muted-foreground">sign in to continue</p>

        {step === 'email' ? (
          <form onSubmit={sendCode} className="flex flex-col gap-3">
            <Input
              type="email"
              placeholder="your email"
              autoComplete="email"
              autoFocus
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
            <Button type="submit" className="w-full">send code</Button>
          </form>
        ) : (
          <form onSubmit={e => { e.preventDefault(); verify() }} className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground text-center">
              enter the 6-digit code sent to <span className="font-medium text-foreground">{email}</span>
            </p>
            <div className="flex gap-2 justify-center">
              {digits.map((d, i) => (
                <input
                  key={i}
                  ref={el => { digitRefs.current[i] = el }}
                  type="text"
                  maxLength={1}
                  inputMode="numeric"
                  className="w-11 h-13 text-center text-xl font-semibold font-mono border border-input rounded-lg outline-none focus:border-primary focus:ring-2 focus:ring-ring/30"
                  value={d}
                  onChange={e => handleDigitInput(i, e.target.value)}
                  onKeyDown={e => handleDigitKeyDown(i, e)}
                  onPaste={handlePaste}
                />
              ))}
            </div>
            <Button type="submit" className="w-full">verify</Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => { setStep('email'); setDigits(['', '', '', '', '', '']); setError('') }}
            >
              use a different email
            </Button>
          </form>
        )}

        {error && <p className="text-sm text-destructive text-center">{error}</p>}
        {status && <p className="text-sm text-primary text-center">{status}</p>}
      </div>
    </div>
  )
}
