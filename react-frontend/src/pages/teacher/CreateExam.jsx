import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import DashboardLayout from '../../components/DashboardLayout'
import Spinner from '../../components/Spinner'
import { apiRequest } from '../../utils/api'

const NAV = [
  { to: '/teacher', icon: '⊞', label: 'Dashboard' },
  { to: '/teacher/create-exam', icon: '✚', label: 'Create Exam' },
  { to: '/teacher/submissions', icon: '📋', label: 'Submissions' },
  { to: '/teacher/results', icon: '🏆', label: 'Results' },
  { to: '/teacher/students', icon: '👥', label: 'Students' },
  { to: '/teacher/analytics', icon: '📊', label: 'Analytics' },
]

export default function CreateExam() {
  const navigate = useNavigate()
  const [courses, setCourses] = useState([])
  const [form, setForm] = useState({ course_id: '', subject: 'database_fundamentals', num_questions: 10, difficulty: 'medium', mcq_count: 6, short_count: 2, long_count: 2 })
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    apiRequest('/teacher/courses').then(res => setCourses(res.data?.courses || []))
  }, [])

  function update(field, value) { setForm(prev => ({ ...prev, [field]: value })) }

  async function handleGenerate(e) {
    e.preventDefault()
    if (!file) { setError('Please upload a file.'); return }
    setError(''); setLoading(true); setStatus('Checking AI server...')
    try {
      const token = await (await import('../../utils/api')).getAccessToken()
      const fd = new FormData()
      fd.append('file', file)
      Object.entries(form).forEach(([k, v]) => fd.append(k, v))

      setStatus('Generating questions with AI...')
      const base = (await import('../../utils/api')).getBackendBase()
      const res = await fetch(`${base}/generate-questions`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Generation failed')

      setStatus(`Generated ${data.questions_count || 0} questions!`)
      if (data.exam_id) {
        setTimeout(() => navigate(`/teacher/question-editor?exam_id=${data.exam_id}`), 1200)
      }
    } catch (err) {
      setError(err.message)
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  const subjects = [
    ['database_fundamentals', 'Database Systems'],
    ['python_programming', 'Python Programming'],
    ['web_development', 'Web Development'],
    ['software_engineering', 'Software Engineering'],
    ['object_oriented_programming', 'Object Oriented Programming'],
    ['data_structures', 'Data Structures'],
    ['algorithms', 'Algorithms'],
    ['general', 'General'],
  ]

  return (
    <DashboardLayout navLinks={NAV} title="Create Exam">
      <div style={{ maxWidth: 700 }}>
        <div style={{ marginBottom: '1.2rem', background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10, padding: '1rem 1.2rem' }}>
          <h1 style={{ fontSize: '1.3rem', fontWeight: 800, color: '#1E3A8A', margin: 0 }}>Create New Exam</h1>
          <p style={{ color: '#6B7280', fontSize: 13, margin: '4px 0 0' }}>Upload course material and AI will generate exam questions automatically.</p>
        </div>

        <form onSubmit={handleGenerate} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* File Upload */}
          <div style={{ background: '#fff', border: '2px dashed #BFDBFE', borderRadius: 10, padding: '1.5rem', textAlign: 'center' }}>
            <input type="file" accept=".pdf,.docx,.doc,.pptx,.ppt" onChange={e => setFile(e.target.files[0])} style={{ display: 'none' }} id="fileInput" />
            <label htmlFor="fileInput" style={{ cursor: 'pointer' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>📄</div>
              <div style={{ color: '#1E3A8A', fontWeight: 700, fontSize: 14 }}>{file ? file.name : 'Click to upload course material'}</div>
              <div style={{ color: '#6B7280', fontSize: 12, marginTop: 4 }}>PDF, DOCX, PPT supported</div>
            </label>
          </div>

          <div style={{ background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10, padding: '1.2rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div>
              <label style={{ display: 'block', color: '#1E3A8A', fontSize: 12, fontWeight: 700, marginBottom: 6, textTransform: 'uppercase' }}>Course</label>
              <select value={form.course_id} onChange={e => update('course_id', e.target.value)}
                style={{ width: '100%', border: '1px solid #DBEAFE', borderRadius: 8, padding: '8px 10px', fontSize: 13, outline: 'none', background: '#F8FAFC' }}>
                <option value="">Select course...</option>
                {courses.map(c => <option key={c.id} value={c.id}>{c.course_code} — {c.course_name}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', color: '#1E3A8A', fontSize: 12, fontWeight: 700, marginBottom: 6, textTransform: 'uppercase' }}>Subject</label>
              <select value={form.subject} onChange={e => update('subject', e.target.value)}
                style={{ width: '100%', border: '1px solid #DBEAFE', borderRadius: 8, padding: '8px 10px', fontSize: 13, outline: 'none', background: '#F8FAFC' }}>
                {subjects.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', color: '#1E3A8A', fontSize: 12, fontWeight: 700, marginBottom: 6, textTransform: 'uppercase' }}>Difficulty</label>
              <select value={form.difficulty} onChange={e => update('difficulty', e.target.value)}
                style={{ width: '100%', border: '1px solid #DBEAFE', borderRadius: 8, padding: '8px 10px', fontSize: 13, outline: 'none', background: '#F8FAFC' }}>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', color: '#1E3A8A', fontSize: 12, fontWeight: 700, marginBottom: 6, textTransform: 'uppercase' }}>Total Questions</label>
              <input type="number" min={5} max={30} value={form.num_questions} onChange={e => update('num_questions', parseInt(e.target.value))}
                style={{ width: '100%', border: '1px solid #DBEAFE', borderRadius: 8, padding: '8px 10px', fontSize: 13, outline: 'none', background: '#F8FAFC' }} />
            </div>
            {[['mcq_count', 'MCQ Count'], ['short_count', 'Short Answer'], ['long_count', 'Long Answer']].map(([field, label]) => (
              <div key={field}>
                <label style={{ display: 'block', color: '#1E3A8A', fontSize: 12, fontWeight: 700, marginBottom: 6, textTransform: 'uppercase' }}>{label}</label>
                <input type="number" min={0} max={20} value={form[field]} onChange={e => update(field, parseInt(e.target.value))}
                  style={{ width: '100%', border: '1px solid #DBEAFE', borderRadius: 8, padding: '8px 10px', fontSize: 13, outline: 'none', background: '#F8FAFC' }} />
              </div>
            ))}
          </div>

          {error && <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: 8, padding: '10px 14px', color: '#7f1d1d', fontSize: 13 }}>{error}</div>}
          {status && <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '10px 14px', color: '#1e3a8a', fontSize: 13, display: 'flex', alignItems: 'center', gap: 10 }}>
            {loading && <Spinner size={16} />} {status}
          </div>}

          <button type="submit" disabled={loading}
            style={{ background: loading ? '#94a3b8' : '#1E3A8A', color: '#fff', border: 'none', borderRadius: 9, padding: '12px', fontSize: 14, fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer' }}>
            {loading ? 'Generating...' : 'Generate Questions with AI'}
          </button>
        </form>
      </div>
    </DashboardLayout>
  )
}
