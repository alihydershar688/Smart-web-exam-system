import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children, allowedRoles }) {
  const { user, profile, loading } = useAuth()

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#F0F4FF' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ width: 40, height: 40, border: '3px solid rgba(30,58,138,0.15)', borderTop: '3px solid #1E3A8A', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 12px' }} />
          <p style={{ color: '#6B7280', fontSize: 14 }}>Loading...</p>
        </div>
      </div>
    )
  }

  if (!user || !profile) return <Navigate to="/login" replace />
  if (profile.status !== 'active') return <Navigate to="/login?reason=pending" replace />
  if (allowedRoles && !allowedRoles.includes(profile.role)) {
    const roleMap = { student: '/student', teacher: '/teacher', admin: '/admin', super_admin: '/super-admin' }
    return <Navigate to={roleMap[profile.role] || '/login'} replace />
  }

  return children
}
