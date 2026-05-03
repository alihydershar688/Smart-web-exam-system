import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { supabase } from '../utils/supabase'
import { apiRequest } from '../utils/api'

export default function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('student')
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleLogin(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data, error: authErr } = await supabase.auth.signInWithPassword({ email, password })
      if (authErr) throw new Error(authErr.message)

      const { data: profile } = await supabase.from('users').select('*').eq('email', email).single()
      if (!profile) throw new Error('Account not found.')
      if (profile.status === 'pending') throw new Error('Your account is pending admin approval.')
      if (profile.status !== 'active') throw new Error('Your account is not active.')

      const roleMap = { student: '/student', teacher: '/teacher', admin: '/admin', super_admin: '/super-admin' }
      navigate(roleMap[profile.role] || '/student', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #050D1A 0%, #08142D 50%, #0A1E46 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ width: '100%', maxWidth: 400, background: 'rgba(8,20,45,0.95)', border: '1px solid rgba(30,100,220,0.22)', borderRadius: 18, padding: '2rem', boxShadow: '0 24px 60px rgba(0,0,0,0.5)' }}>
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: 'linear-gradient(135deg, #1A6EFF, #0A3FAA)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px', fontSize: 18, fontWeight: 800, color: '#fff' }}>SE</div>
          <h1 style={{ color: '#E8F2FF', fontSize: '1.4rem', fontWeight: 800, margin: 0 }}>Smart Exam System</h1>
          <p style={{ color: '#7BAEDD', fontSize: 13, marginTop: 4 }}>Sign in to your account</p>
        </div>

        {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '10px 14px', color: '#fca5a5', fontSize: 13, marginBottom: 16 }}>{error}</div>}

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ display: 'block', color: '#7BAEDD', fontSize: 12, fontWeight: 700, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Email Address</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@example.com"
              style={{ width: '100%', background: '#0A1E46', border: '1px solid rgba(30,100,220,0.22)', borderRadius: 9, padding: '9px 12px', color: '#E8F2FF', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
          </div>
          <div>
            <label style={{ display: 'block', color: '#7BAEDD', fontSize: 12, fontWeight: 700, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Password</label>
            <div style={{ position: 'relative' }}>
              <input type={showPass ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} required placeholder="••••••••"
                style={{ width: '100%', background: '#0A1E46', border: '1px solid rgba(30,100,220,0.22)', borderRadius: 9, padding: '9px 40px 9px 12px', color: '#E8F2FF', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
              <button type="button" onClick={() => setShowPass(!showPass)} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#7BAEDD', cursor: 'pointer', fontSize: 12 }}>
                {showPass ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>
          <div>
            <label style={{ display: 'block', color: '#7BAEDD', fontSize: 12, fontWeight: 700, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Role</label>
            <select value={role} onChange={e => setRole(e.target.value)}
              style={{ width: '100%', background: '#0A1E46', border: '1px solid rgba(30,100,220,0.22)', borderRadius: 9, padding: '9px 12px', color: '#E8F2FF', fontSize: 13, outline: 'none', boxSizing: 'border-box' }}>
              <option value="student">Student</option>
              <option value="teacher">Teacher / Lecturer</option>
              <option value="admin">Administrator</option>
            </select>
          </div>
          <button type="submit" disabled={loading}
            style={{ background: 'linear-gradient(135deg, #1A6EFF, #0A3FAA)', color: '#fff', border: 'none', borderRadius: 9, padding: '10px', fontSize: 13, fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.7 : 1, marginTop: 4 }}>
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: 16 }}>
          <span style={{ color: '#4A7AAA', fontSize: 13 }}>Don't have an account? </span>
          <Link to="/signup" style={{ color: '#7BAEDD', fontSize: 13, fontWeight: 700 }}>Create Account</Link>
        </div>
        <div style={{ textAlign: 'center', marginTop: 8 }}>
          <Link to="/reset-password" style={{ color: '#4A7AAA', fontSize: 12 }}>Forgot password?</Link>
        </div>
      </div>
    </div>
  )
}
