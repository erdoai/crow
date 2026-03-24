import { useEffect, useRef, useState } from 'react'
import { Sun, Moon, Monitor } from 'lucide-react'
import { useTheme } from './theme-provider'
import { Button } from '@/components/ui/button'

const options = [
  { value: 'system' as const, label: 'System', icon: Monitor },
  { value: 'light' as const, label: 'Light', icon: Sun },
  { value: 'dark' as const, label: 'Dark', icon: Moon },
]

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const ActiveIcon = options.find(o => o.value === theme)!.icon

  return (
    <div ref={ref} className={`relative ${className ?? ''}`}>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen(o => !o)}
        aria-label="Toggle theme"
      >
        <ActiveIcon className="h-4 w-4" />
      </Button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 min-w-[120px] rounded-md border bg-popover p-1 shadow-md">
          {options.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              className={`flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm transition-colors hover:bg-accent hover:text-accent-foreground ${
                theme === value ? 'bg-accent text-accent-foreground' : 'text-popover-foreground'
              }`}
              onClick={() => { setTheme(value); setOpen(false) }}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
