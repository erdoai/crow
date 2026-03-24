import { createContext, useContext, useEffect, useState } from 'react'

type Theme = 'system' | 'light' | 'dark'

type ThemeContext = {
  theme: Theme
  setTheme: (theme: Theme) => void
}

const ThemeContext = createContext<ThemeContext>({ theme: 'system', setTheme: () => {} })

const STORAGE_KEY = 'crow-theme'

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    return (localStorage.getItem(STORAGE_KEY) as Theme) || 'system'
  })

  useEffect(() => {
    const root = document.documentElement

    function apply() {
      if (theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        root.classList.add('dark')
      } else {
        root.classList.remove('dark')
      }
    }

    apply()
    localStorage.setItem(STORAGE_KEY, theme)

    if (theme === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)')
      mq.addEventListener('change', apply)
      return () => mq.removeEventListener('change', apply)
    }
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}
