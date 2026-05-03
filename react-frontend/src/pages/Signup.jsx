import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { supabase } from '../utils/supabase'

function generateId(role) {
  const prefix = role === 'student' ? 'S' : role === 'teacher' ? 'T' : 'A'
  return `${prefix}-${Math.floor(10000 + Math.random() * 90000)}`
}

export default function Signup() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ firstName: '', lastName: '', email: '', password: '', role: 'student' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  function update(field, value) { setForm(prev => ({ ...prev, [field]: value })) }

  async function handleSignup(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data, error: authErr } = await supabase.auth.signUp({ email: form.email, password: form.password })
      if (authErr) throw new Error(authErr.message)

      const userId = data.user?.id
      const uniqueId = generateId(form.role)
      await supabase.from('users').insert({
        id: userId,
        email: form.email,
        first_name: form.firstName,
        last_name: form.lastName,
        full_name: `${form.firstName} ${form.lastName}`.trim(),
        role: form.role,
        status: 'pending',
        student_id: form.role === 'student' ? uniqueId : null,
        teacher_id: form.role === 'teacher' ? uniqueId : null,
        admin_id: form.role === 'admin' ? uniqueId : null,
      })
      setSuccess(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (success) return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #050D1A, #08142D)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ background: 'rgba(8,20,45,0.95)', border: '1px solid rgba(30,100,220,0.22)', borderRadius: 18, padding: '2rem', maxWidth: 400, width: '100%', textAlign: 'center' }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>✓</div>
        <h2 style={{ color: '#E8F2FF', marginBottom: 8 }}>Registration Submitted</h2>
        <p style={{ color: '#7BAEDD', fontSize: 14, marginBottom: 20 }}>Your account is pending admin approval. You'll receive an email once approved.</p>
        <Link to="/login" style={{ background: 'linear-gradient(135deg, #1A6EFF, #0A3FAA)', color: '#fff', padding: '10px 24px', borderRadius: 9, textDecoration: 'none', fontWeight: 700, fontSize: 13 }}>Back to Login</Link>
      </div>
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #050D1A, #08142D)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ width: '100%', maxWidth: 420, background: 'rgba(8,20,45,0.95)', border: '1px solid rgba(30,100,220,0.22)', borderRadius: 18, padding: '2rem', boxShadow: '0 24px 60px rgba(0,0,0,0.5)' }}>
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <h1 style={{ color: '#E8F2FF', fontSize: '1.3rem', fontWeight: 800 }}>Create Account</h1>
          <p style={{ color: '#7BAEDD', fontSize: 13 }}>Join Smart Exam System</p>
        </div>

        {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '10px 14px', color: '#fca5a5', fontSize: 13, marginBottom: 16 }}>{error}</div>}

        <form onSubmit={handleSignup} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {[['firstName', 'First Name'], ['lastName', 'Last Name']].map(([field, label]) => (
              <div key={field}>
                <label style={{ display: 'block', color: '#7BAEDD', fontSize: 11, fontWeight: 700, marginBottom: 5, textTransform: 'uppercase' }}>{label}</label>
                <input value={form[field]} onChange={e => update(field, e.target.value)} required placeholder={label}
                  style={{ width: '100%', background: '#0A1E46', border: '1px solid rgba(30,100,220,0.22)', borderRadius: 8, padding: '8px 10px', color: '#E8F2FF', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
              </div>
            ))}
          </div>
          {[['email', 'Email', 'email', 'you@example.com'], ['password', 'Password', 'password', '••••••••']].map(([field, label, type, ph]) => (
            <div key={field}>
              <label style={{ display: 'block', color: '#7BAEDD', fontSize: 11, fontWeight: 700, marginBottom: 5, textTransform: 'uppercase' }}>{label}</label>
              <input type={type} value={form[field]} onChange={e => update(field, e.target.value)} required placeholder={ph}
                style={{ width: '100%', background: '#0A1E46', border: '1px solid rgba(30,100,220,0.22)', borderRadius: 8, padding: '8px 10px', color: '#E8F2FF', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
            </div>
          ))}
          <div>
            <label style={{ display: 'block', color: '#7BAEDD', fontSize: 11, fontWeight: 700, marginBottom: 5, textTransform: 'uppercase' }}>Role</label>
            <select value={form.role} onChange={e => update('role', e.target.value)}
              style={{ width: '100%', background: '#0A1E46', border: '1px solid rgba(30,100,220,0.22)', borderRadius: 8, padding: '8px 10px', color: '#E8F2FF', fontSize: 13, outline: 'none', boxSizing: 'border-box' }}>
              <option value="student">Student</option>
              <option value="teacher">Teacher / Lecturer</option>
            </select>
          </div>
          <button type="submit" disabled={loading}
            style={{ background: 'linear-gradient(135deg, #1A6EFF, #0A3FAA)', color: '#fff', border: 'none', borderRadius: 9, padding: 10, fontSize: 13, fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.7 : 1, marginTop: 4 }}>
            {loading ? 'Creating account...' : 'Create Account'}
          </button>
        </form>
        <div style={{ textAlign: 'center', marginTop: 14 }}>
          <span style={{ color: '#4A7AAA', fontSize: 13 }}>Already have an account? </span>
          <Link to="/login" style={{ color: '#7BAEDD', fontSize: 13, fontWeight: 700 }}>Sign In</Link>
        </div>
      </div>
    </div>
  )
}
