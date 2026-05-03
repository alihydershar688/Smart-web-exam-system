import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function DashboardLayout({ children, navLinks, title, subtitle }) {
  const { profile, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const initials = profile
    ? `${profile.first_name?.[0] || ''}${profile.last_name?.[0] || ''}`.toUpperCase() || 'U'
    : 'U'

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div style={{ minHeight: '100vh', background: '#F0F4FF', fontFamily: 'Manrope, sans-serif' }}>
      {/* Navbar */}
      <nav style={{ position: 'sticky', top: 0, zIndex: 1000, background: '#1E3A8A', borderBottom: '1px solid #DBEAFE', boxShadow: '0 2px 8px rgba(30,58,138,0.07)' }}>
        <div style={{ minHeight: 68, display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setSidebarOpen(!sidebarOpen)} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', padding: 8, display: 'flex', flexDirection: 'column', gap: 5 }}>
              <span style={{ display: 'block', width: 18, height: 2, background: '#fff', borderRadius: 2 }} />
              <span style={{ display: 'block', width: 18, height: 2, background: '#fff', borderRadius: 2 }} />
              <span style={{ display: 'block', width: 18, height: 2, background: '#fff', borderRadius: 2 }} />
            </button>
            <div>
              <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.14em', color: '#93C5FD', fontWeight: 800 }}>Smart Exam System</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>{title}</div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'linear-gradient(135deg, #991b1b, #be123c)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13 }}>
              {initials}
            </div>
          </div>
        </div>
      </nav>

      <div style={{ display: 'flex', padding: 16, gap: 16, alignItems: 'flex-start' }}>
        {/* Sidebar */}
        <aside style={{
          width: 240, minWidth: 240, flexShrink: 0,
          position: 'sticky', top: 84,
          height: 'calc(100vh - 100px)', maxHeight: 'calc(100vh - 100px)',
          background: '#1E3A8A', borderRadius: 14, border: '1px solid #DBEAFE',
          boxShadow: '0 4px 16px rgba(30,58,138,0.1)', padding: '1rem',
          display: 'flex', flexDirection: 'column', overflowY: 'auto',
          transition: 'transform 0.2s ease',
          ...(sidebarOpen ? {} : { transform: window.innerWidth < 1024 ? 'translateX(-120%)' : 'none', position: window.innerWidth < 1024 ? 'fixed' : 'sticky', zIndex: 500, left: 16 })
        }}>
          <div style={{ marginBottom: '0.75rem', paddingBottom: '0.75rem', borderBottom: '1px solid rgba(219,234,254,0.2)' }}>
            <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.14em', color: '#60A5FA', fontWeight: 800, marginBottom: 8 }}>Navigation</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg, #1E3A8A, #2563EB)', border: '1px solid rgba(96,165,250,0.3)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 12 }}>{initials}</div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 800, color: '#CBD5E8' }}>{profile?.first_name || 'User'}</div>
                <div style={{ fontSize: 11, color: '#6B7280' }}>{profile?.role}</div>
              </div>
            </div>
          </div>

          <nav style={{ display: 'grid', gap: 4, flex: 1 }}>
            {navLinks.map(link => {
              const isActive = location.pathname === link.to
              return (
                <Link key={link.to} to={link.to} onClick={() => setSidebarOpen(false)} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '0.65rem 0.8rem',
                  borderRadius: 10, textDecoration: 'none', fontSize: 13, fontWeight: 700,
                  color: isActive ? '#fff' : 'rgba(203,213,232,0.9)',
                  background: isActive ? 'linear-gradient(135deg, rgba(59,130,246,0.25), rgba(37,99,235,0.15))' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${isActive ? 'rgba(96,165,250,0.4)' : 'transparent'}`,
                  transition: 'all 0.18s ease'
                }}>
                  <span style={{ fontSize: 16 }}>{link.icon}</span>
                  {link.label}
                </Link>
              )
            })}
          </nav>

          <div style={{ marginTop: 'auto', paddingTop: '0.75rem', borderTop: '1px solid rgba(219,234,254,0.2)' }}>
            <button onClick={handleLogout} style={{
              width: '100%', background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.2)',
              color: '#FDA8A8', borderRadius: 8, padding: '0.5rem 0.8rem', fontWeight: 600,
              fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6
            }}>
              ↩ Logout
            </button>
          </div>
        </aside>

        {/* Main content */}
        <main style={{ flex: 1, minWidth: 0, borderLeft: '1px solid #DBEAFE', paddingLeft: 20 }}>
          {children}
        </main>
      </div>
    </div>
  )
}
