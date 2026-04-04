import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './hooks/useAuth'
import LoginPage from './pages/LoginPage'
import SettingsPage from './pages/SettingsPage'
import ChatPage from './pages/ChatPage'
import SharedAgentPage from './pages/SharedAgentPage'
import { Toaster } from './components/ui/sonner'

function RequireAuth({ children, user }: {
  children: React.ReactNode
  user: { display_name: string | null } | null
}) {
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  const { user, loading, refetch } = useAuth()

  if (loading) return null

  return (
    <>
    <Toaster />
    <Routes>
      <Route path="/login" element={
        user && user.id !== 'default'
          ? <Navigate to="/" replace />
          : <LoginPage onSuccess={refetch} />
      } />
      <Route path="/settings" element={
        <RequireAuth user={user}>
          <SettingsPage />
        </RequireAuth>
      } />
      <Route path="/chat/:conversationId" element={
        <RequireAuth user={user}>
          <ChatPage />
        </RequireAuth>
      } />
      <Route path="/shared/:token" element={<SharedAgentPage />} />
      {/* Redirect old routes */}
      <Route path="/dashboard" element={<Navigate to="/settings" replace />} />
      <Route path="/onboarding" element={<Navigate to="/" replace />} />
      <Route path="*" element={
        user
          ? <RequireAuth user={user}><ChatPage /></RequireAuth>
          : <Navigate to="/login" replace />
      } />
    </Routes>
    </>
  )
}
