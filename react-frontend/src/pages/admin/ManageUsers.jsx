import { useEffect, useState } from 'react'
import DashboardLayout from '../../components/DashboardLayout'
import Spinner from '../../components/Spinner'
import { apiRequest } from '../../utils/api'

const NAV = [
  { to: '/admin', icon: '⊞', label: 'Dashboard' },
  { to: '/admin/users', icon: '👥', label: 'Manage Users' },
  { to: '/admin/analytics', icon: '📊', label: 'Analytics' },
  { to: '/admin/profile', icon: '👤', label: 'Profile' },
]

const ROLE_COLORS = { student: ['#DBEAFE', '#0C2340'], teacher: ['#BFDBFE', '#0C2340'], admin: ['#FEF08A', '#713F12'], super_admin: ['#EDE9FE', '#4C1D95'] }
const STATUS_COLORS = { active: ['#DCFCE7', '#14532D'], pending: ['#FEF3C7', '#92400E'], suspended: ['#FECACA', '#7F1D1D'] }

export default function ManageUsers() {
  const [users, setUsers] = useState([])
  const [filtered, setFiltered] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [toast, setToast] = useState('')

  useEffect(() => { loadUsers() }, [])
  useEffect(() => { applyFilters() }, [users, search, roleFilter, statusFilter])

  async function loadUsers() {
    setLoading(true)
    try {
      const res = await apiRequest('/admin/users')
      if (res.status === 401 || res.status === 403) { setToast('Session expired. Please log in again.'); return }
      setUsers(res.data?.users || [])
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  function applyFilters() {
    let list = [...users]
    if (search) list = list.filter(u => `${u.first_name} ${u.last_name} ${u.email}`.toLowerCase().includes(search.toLowerCase()))
    if (roleFilter) list = list.filter(u => u.role === roleFilter)
    if (statusFilter) list = list.filter(u => u.status === statusFilter)
    setFiltered(list)
  }

  async function updateStatus(email, status) {
    await apiRequest('/admin/users/status', { method: 'PUT', body: JSON.stringify({ user_email: email, status }) })
    setToast(`User ${status === 'active' ? 'approved' : 'updated'} successfully`)
    setTimeout(() => setToast(''), 3000)
    loadUsers()
  }

  const badge = (text, colors) => (
    <span style={{ background: colors[0], color: colors[1], padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 700 }}>{text}</span>
  )

  return (
    <DashboardLayout navLinks={NAV} title="Manage Users">
      {toast && <div style={{ position: 'fixed', top: 20, right: 20, background: '#1F2937', color: '#fff', padding: '10px 16px', borderRadius: 8, borderLeft: '4px solid #10b981', zIndex: 9999, fontSize: 13, fontWeight: 600 }}>{toast}</div>}

      <div style={{ marginBottom: '1.2rem', background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10, padding: '1rem 1.2rem' }}>
        <h1 style={{ fontSize: '1.3rem', fontWeight: 800, color: '#1E3A8A', margin: 0 }}>User Management</h1>
        <p style={{ color: '#6B7280', fontSize: 13, margin: '4px 0 0' }}>Review users, filter by status, and control account availability.</p>
      </div>

      {/* Filters */}
      <div style={{ background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10, padding: '1rem', marginBottom: '1rem', display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by name or email..."
          style={{ flex: 1, minWidth: 200, border: '1px solid #DBEAFE', borderRadius: 8, padding: '7px 12px', fontSize: 13, outline: 'none', background: '#F8FAFC' }} />
        <select value={roleFilter} onChange={e => setRoleFilter(e.target.value)}
          style={{ border: '1px solid #DBEAFE', borderRadius: 8, padding: '7px 12px', fontSize: 13, outline: 'none', background: '#F8FAFC' }}>
          <option value="">All Roles</option>
          <option value="student">Student</option>
          <option value="teacher">Teacher</option>
          <option value="admin">Admin</option>
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          style={{ border: '1px solid #DBEAFE', borderRadius: 8, padding: '7px 12px', fontSize: 13, outline: 'none', background: '#F8FAFC' }}>
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="pending">Pending</option>
          <option value="suspended">Suspended</option>
        </select>
        <span style={{ color: '#6B7280', fontSize: 13 }}>{filtered.length} users</span>
      </div>

      <div style={{ background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10, overflow: 'hidden', boxShadow: '0 2px 8px rgba(30,58,138,0.07)' }}>
        {loading ? <div style={{ textAlign: 'center', padding: '3rem' }}><Spinner /></div> : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 700 }}>
              <thead>
                <tr style={{ background: '#1E3A8A' }}>
                  {['Name', 'Email', 'Role', 'Status', 'Joined', 'Actions'].map(h => (
                    <th key={h} style={{ padding: '0.75rem 0.9rem', textAlign: 'left', color: '#fff', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: '#6B7280', fontSize: 14 }}>No users found.</td></tr>
                ) : filtered.map((u, i) => (
                  <tr key={u.id || i} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFC', borderBottom: '1px solid #E0E7FF' }}>
                    <td style={{ padding: '0.7rem 0.9rem', color: '#1F2937', fontWeight: 600, fontSize: 13 }}>{u.first_name} {u.last_name}</td>
                    <td style={{ padding: '0.7rem 0.9rem', color: '#6B7280', fontSize: 13 }}>{u.email}</td>
                    <td style={{ padding: '0.7rem 0.9rem' }}>{badge(u.role, ROLE_COLORS[u.role] || ['#F3F4F6', '#374151'])}</td>
                    <td style={{ padding: '0.7rem 0.9rem' }}>{badge(u.status, STATUS_COLORS[u.status] || ['#F3F4F6', '#374151'])}</td>
                    <td style={{ padding: '0.7rem 0.9rem', color: '#6B7280', fontSize: 12 }}>{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                    <td style={{ padding: '0.7rem 0.9rem' }}>
                      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                        {u.status === 'pending' && <button onClick={() => updateStatus(u.email, 'active')} style={{ background: '#10b981', color: '#fff', border: 'none', borderRadius: 6, padding: '4px 10px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>Approve</button>}
                        {u.status === 'active' && u.role !== 'super_admin' && <button onClick={() => updateStatus(u.email, 'suspended')} style={{ background: '#fee2e2', color: '#7f1d1d', border: '1px solid #fca5a5', borderRadius: 6, padding: '4px 10px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>Suspend</button>}
                        {u.status === 'suspended' && <button onClick={() => updateStatus(u.email, 'active')} style={{ background: '#DBEAFE', color: '#1E3A8A', border: '1px solid #BFDBFE', borderRadius: 6, padding: '4px 10px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>Restore</button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
