import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import DashboardLayout from '../../components/DashboardLayout'
import StatCard from '../../components/StatCard'
import Spinner from '../../components/Spinner'
import { apiRequest } from '../../utils/api'

const NAV = [
  { to: '/admin', icon: '⊞', label: 'Dashboard' },
  { to: '/admin/users', icon: '👥', label: 'Manage Users' },
  { to: '/admin/analytics', icon: '📊', label: 'Analytics' },
  { to: '/admin/profile', icon: '👤', label: 'Profile' },
]

export default function AdminDashboard() {
  const navigate = useNavigate()
  const [stats, setStats] = useState({})
  const [pending, setPending] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadData() }, [])

  async function loadData() {
    setLoading(true)
    try {
      const res = await apiRequest('/admin/users')
      const users = res.data?.users || []
      const pendingUsers = users.filter(u => u.status === 'pending')
      setPending(pendingUsers.slice(0, 5))
      setStats({
        total: users.length,
        active: users.filter(u => u.status === 'active').length,
        pending: pendingUsers.length,
        teachers: users.filter(u => u.role === 'teacher').length,
        students: users.filter(u => u.role === 'student').length,
      })
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  async function approveUser(email) {
    await apiRequest('/admin/users/status', { method: 'PUT', body: JSON.stringify({ user_email: email, status: 'active' }) })
    loadData()
  }

  return (
    <DashboardLayout navLinks={NAV} title="Admin Dashboard">
      <div style={{ marginBottom: '1.2rem', background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10, padding: '1rem 1.2rem', boxShadow: '0 2px 8px rgba(30,58,138,0.07)' }}>
        <h1 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#1E3A8A', margin: 0 }}>Admin Dashboard</h1>
        <p style={{ color: '#6B7280', fontSize: 13, margin: '4px 0 0' }}>Manage users, approve registrations, and monitor the platform.</p>
      </div>

      {loading ? <div style={{ textAlign: 'center', padding: '3rem' }}><Spinner /></div> : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: '1.2rem' }}>
            <StatCard label="Total Users" value={stats.total ?? 0} footer="All accounts" accent="#2563EB" onClick={() => navigate('/admin/users')} />
            <StatCard label="Active Users" value={stats.active ?? 0} footer="Approved accounts" accent="#10b981" />
            <StatCard label="Pending Approval" value={stats.pending ?? 0} footer="Awaiting review" accent="#F59E0B" onClick={() => navigate('/admin/users?filter=pending')} />
            <StatCard label="Teachers" value={stats.teachers ?? 0} footer="Registered teachers" accent="#6366f1" />
            <StatCard label="Students" value={stats.students ?? 0} footer="Registered students" accent="#14b8a6" />
          </div>

          {pending.length > 0 && (
            <div style={{ background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10, padding: '1rem', boxShadow: '0 2px 8px rgba(30,58,138,0.07)', marginBottom: '1.2rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', paddingBottom: '0.75rem', borderBottom: '1px solid #DBEAFE' }}>
                <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: '#1E3A8A' }}>Pending Approvals</h3>
                <span style={{ background: '#FEF3C7', color: '#92400E', padding: '2px 10px', borderRadius: 999, fontSize: 12, fontWeight: 700 }}>{stats.pending} pending</span>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#1E3A8A' }}>
                    {['Name', 'Email', 'Role', 'Action'].map(h => (
                      <th key={h} style={{ padding: '0.65rem 0.85rem', textAlign: 'left', color: '#fff', fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pending.map((u, i) => (
                    <tr key={u.id || i} style={{ borderBottom: '1px solid #E0E7FF' }}>
                      <td style={{ padding: '0.65rem 0.85rem', color: '#1F2937', fontWeight: 600, fontSize: 13 }}>{u.first_name} {u.last_name}</td>
                      <td style={{ padding: '0.65rem 0.85rem', color: '#6B7280', fontSize: 13 }}>{u.email}</td>
                      <td style={{ padding: '0.65rem 0.85rem' }}>
                        <span style={{ background: '#DBEAFE', color: '#1E3A8A', padding: '2px 8px', borderRadius: 6, fontSize: 12, fontWeight: 700 }}>{u.role}</span>
                      </td>
                      <td style={{ padding: '0.65rem 0.85rem' }}>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button onClick={() => approveUser(u.email)} style={{ background: '#10b981', color: '#fff', border: 'none', borderRadius: 6, padding: '4px 12px', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>Approve</button>
                          <button style={{ background: '#fee2e2', color: '#7f1d1d', border: '1px solid #fca5a5', borderRadius: 6, padding: '4px 12px', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>Reject</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </DashboardLayout>
  )
}
