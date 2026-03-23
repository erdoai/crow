import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './hooks/useAuth'
import LoginPage from './pages/LoginPage'
import OnboardingPage from './pages/OnboardingPage'
import DashboardPage from './pages/DashboardPage'
import ChatPage from './pages/ChatPage'

function RequireAuth({ children, user, authEnabled }: {
  children: React.ReactNode
  user: { display_name: string | null } | null
  authEnabled: boolean
}) {
  if (!user) return <Navigate to="/login" replace />
  if (authEnabled && !user.display_name) return <Navigate to="/onboarding" replace />
  return <>{children}</>
}

export default function App() {
  const { user, loading, refetch } = useAuth()

  if (loading) return null

  const authEnabled = user?.auth_enabled ?? true

  return (
    <Routes>
      <Route path="/login" element={
        user && user.id !== 'default'
          ? <Navigate to="/dashboard" replace />
          : <LoginPage onSuccess={refetch} />
      } />
      <Route path="/onboarding" element={
        <OnboardingPage onSuccess={refetch} />
      } />
      <Route path="/dashboard" element={
        <RequireAuth user={user} authEnabled={authEnabled}>
          <DashboardPage />
        </RequireAuth>
      } />
      <Route path="/chat" element={
        <RequireAuth user={user} authEnabled={authEnabled}>
          <ChatPage />
        </RequireAuth>
      } />
      <Route path="/chat/:conversationId" element={
        <RequireAuth user={user} authEnabled={authEnabled}>
          <ChatPage />
        </RequireAuth>
      } />
      <Route path="*" element={
        <Navigate to={user ? "/dashboard" : "/login"} replace />
      } />
    </Routes>
  )
}
