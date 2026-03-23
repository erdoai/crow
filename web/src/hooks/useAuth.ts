import { useEffect, useState } from 'react'
import { fetchJSON, type User } from '../api'

interface AuthState {
  user: User | null
  loading: boolean
  refetch: () => void
}

export function useAuth(): AuthState {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refetch = () => {
    setLoading(true)
    fetchJSON<User>('/api/me')
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }

  useEffect(refetch, [])

  return { user, loading, refetch }
}
