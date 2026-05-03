import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import DashboardLayout from '../../components/DashboardLayout'
import Spinner from '../../components/Spinner'
import { apiRequest } from '../../utils/api'

const NAV = [
  { to: '/student', icon: '⊞', label: 'Dashboard' },
  { to: '/student/exams', icon: '📋', label: 'Available Exams' },
  { to: '/student/results', icon: '📊', label: 'My Results' },
]

export default function ExamResults() {
  const [params] = useSearchParams()
  const attemptId = params.get('attempt')
  const navigate = useNavigate()
  const [result, setResult] = useState(null)
  const [answers, setAnswers] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!attemptId) { navigate('/student'); return }
    loadResults()
  }, [attemptId])

  async function loadResults() {
    setLoading(true)
    try {
      const res = await apiRequest(`/attempt-results/${attemptId}`)
      setResult(res.data?.attempt)
      setAnswers(res.data?.answers || [])
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const pct = result?.percentage ?? 0
  const circleColor = pct >= 80 ? '#27ae60' : pct >= 60 ? '#3498db' : pct >= 40 ? '#f39c12' : '#e74c3c'

  const statusStyle = (rs) => {
    if (rs === 'correct') return { bg: 'rgba(16,185,129,0.06)', border: '#86efac', badge: ['#dcfce7', '#14532d', 'Correct'] }
    if (rs === 'incorrect') return { bg: 'rgba(239,68,68,0.06)', border: '#fca5a5', badge: ['#fee2e2', '#7f1d1d', 'Incorrect'] }
    return { bg: 'rgba(245,158,11,0.06)', border: '#fcd34d', badge: ['#fef3c7', '#92400e', 'Pending Review'] }
  }

  return (
    <DashboardLayout navLinks={NAV} title="Exam Results">
      {loading ? <div style={{ textAlign: 'center', padding: '3rem' }}><Spinner /></div> : !result ? (
        <p style={{ color: '#6B7280', textAlign: 'center', padding: '3rem' }}>Results not found.</p>
      ) : (
        <div style={{ maxWidth: 860 }}>
          {/* Score header */}
          <div style={{ background: '#fff', border: '1px solid #DBEAFE', borderRadius: 12, padding: '1.5rem', textAlign: 'center', marginBottom: '1.2rem' }}>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 3, color: '#6B7280', marginBottom: 12 }}>Submitted</div>
            <h2 style={{ color: '#1E3A8A', fontSize: '1.5rem', fontWeight: 800, marginBottom: 4 }}>{result.exam_title || 'Exam'}</h2>
            <p style={{ color: '#6B7280', fontSize: 13, marginBottom: 20 }}>{result.subject || ''}</p>
            <div style={{ width: 160, height: 160, borderRadius: '50%', background: circleColor, color: '#fff', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px', boxShadow: `0 8px 24px ${circleColor}44` }}>
              <div style={{ fontSize: 28, fontWeight: 800 }}>{result.score ?? 0}/{result.total_marks ?? 0}</div>
              <div style={{ fontSize: 14, opacity: 0.9 }}>{pct.toFixed(1)}%</div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
              {[
                ['Correct', answers.filter(a => a.is_correct === true).length, '#10b981'],
                ['Incorrect', answers.filter(a => a.is_correct === false).length, '#ef4444'],
                ['Pending Review', answers.filter(a => a.is_correct === null).length, '#f59e0b'],
                ['Time Taken', result.time_taken_minutes ? `${result.time_taken_minutes}m` : '—', '#6366f1'],
              ].map(([label, val, color]) => (
                <div key={label} style={{ background: '#F8FAFC', border: '1px solid #DBEAFE', borderRadius: 10, padding: '0.75rem', textAlign: 'center' }}>
                  <div style={{ fontSize: 22, fontWeight: 800, color }}>{val}</div>
                  <div style={{ fontSize: 11, color: '#6B7280', marginTop: 2 }}>{label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Answers */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {answers.map((ans, i) => {
              const q = ans.questions || {}
              const isCorrect = ans.is_correct === true ? 'correct' : ans.is_correct === false ? 'incorrect' : 'pending'
              const s = statusStyle(isCorrect)
              return (
                <div key={i} style={{ background: s.bg, border: `1px solid ${s.border}`, borderRadius: 12, padding: '1.2rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
                    <span style={{ fontWeight: 700, color: '#1E3A8A', fontSize: 14 }}>Question {i + 1}</span>
                    <span style={{ background: s.badge[0], color: s.badge[1], padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 700 }}>{s.badge[2]}</span>
                  </div>
                  <p style={{ fontSize: 15, fontWeight: 600, color: '#1F2937', marginBottom: 12, lineHeight: 1.6 }}>{q.question_text || q.question || 'Question'}</p>
                  <div style={{ background: 'rgba(255,255,255,0.6)', border: '1px solid rgba(148,163,184,0.2)', borderRadius: 8, padding: '0.75rem', marginBottom: 8 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#6B7280', marginBottom: 4, textTransform: 'uppercase' }}>Your Answer</div>
                    <div style={{ color: '#1F2937', fontSize: 14 }}>{String(ans.student_answer || 'Not answered')}</div>
                  </div>
                  {ans.is_correct === false && q.correct_answer && (
                    <div style={{ background: 'rgba(16,185,129,0.08)', borderLeft: '4px solid #10b981', borderRadius: '0 8px 8px 0', padding: '0.75rem' }}>
                      <span style={{ fontWeight: 700, color: '#065f46', fontSize: 13 }}>Correct Answer: </span>
                      <span style={{ color: '#065f46', fontSize: 13 }}>{q.correct_answer}</span>
                    </div>
                  )}
                  {ans.marks_obtained !== null && ans.marks_obtained !== undefined && (
                    <div style={{ marginTop: 8, fontSize: 13, color: '#6B7280' }}>Marks: <strong style={{ color: '#1E3A8A' }}>{ans.marks_obtained} / {q.marks || 1}</strong></div>
                  )}
                </div>
              )
            })}
          </div>

          <div style={{ marginTop: 20, display: 'flex', gap: 10 }}>
            <button onClick={() => navigate('/student')} style={{ background: '#1E3A8A', color: '#fff', border: 'none', borderRadius: 8, padding: '10px 20px', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>Back to Dashboard</button>
            <button onClick={() => window.print()} style={{ background: '#F0F4FF', color: '#1E3A8A', border: '1px solid #DBEAFE', borderRadius: 8, padding: '10px 20px', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>Print Results</button>
          </div>
        </div>
      )}
    </DashboardLayout>
  )
}
