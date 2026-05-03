import { useEffect, useState, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { apiRequest } from '../../utils/api'
import Spinner from '../../components/Spinner'

export default function TakeExam() {
  const [params] = useSearchParams()
  const examId = params.get('id')
  const navigate = useNavigate()
  const [exam, setExam] = useState(null)
  const [questions, setQuestions] = useState([])
  const [answers, setAnswers] = useState({})
  const [current, setCurrent] = useState(0)
  const [timeLeft, setTimeLeft] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [attemptId, setAttemptId] = useState(null)
  const timerRef = useRef(null)

  useEffect(() => {
    if (!examId) { navigate('/student'); return }
    loadExam()
    return () => clearInterval(timerRef.current)
  }, [examId])

  async function loadExam() {
    setLoading(true)
    try {
      const [examRes, qRes] = await Promise.all([
        apiRequest(`/exams/${examId}`),
        apiRequest(`/exam-questions/${examId}`)
      ])
      const examData = examRes.data?.exam
      const qs = qRes.data?.questions || []
      setExam(examData)
      setQuestions(qs)
      const duration = (examData?.duration_minutes || 60) * 60
      setTimeLeft(duration)
      timerRef.current = setInterval(() => {
        setTimeLeft(t => {
          if (t <= 1) { clearInterval(timerRef.current); handleSubmit(true); return 0 }
          return t - 1
        })
      }, 1000)
      // Start attempt
      const startRes = await apiRequest(`/exams/${examId}/start`, { method: 'POST' })
      if (startRes.data?.attempt_id) setAttemptId(startRes.data.attempt_id)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  function setAnswer(qId, value) {
    setAnswers(prev => ({ ...prev, [qId]: value }))
  }

  async function handleSubmit(autoSubmit = false) {
    if (!autoSubmit && !window.confirm('Submit exam? You cannot change answers after submission.')) return
    setSubmitting(true)
    clearInterval(timerRef.current)
    try {
      const payload = questions.map(q => ({
        question_id: q.question_id || q.id,
        answer: answers[q.question_id || q.id] || ''
      }))
      const res = await apiRequest(`/exams/${examId}/submit`, {
        method: 'POST',
        body: JSON.stringify({ answers: payload, attempt_id: attemptId })
      })
      const aid = res.data?.attempt_id || attemptId
      navigate(`/student/results?attempt=${aid}`)
    } catch (e) {
      console.error(e)
      setSubmitting(false)
    }
  }

  function formatTime(s) {
    const m = Math.floor(s / 60), sec = s % 60
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  }

  const timerColor = timeLeft < 120 ? '#ef4444' : timeLeft < 300 ? '#f59e0b' : '#EF9F27'

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#E6F1FB' }}>
      <div style={{ textAlign: 'center' }}><Spinner size={40} /><p style={{ marginTop: 12, color: '#185FA5' }}>Loading exam...</p></div>
    </div>
  )

  const q = questions[current]

  return (
    <div style={{ minHeight: '100vh', background: '#E6F1FB', fontFamily: 'Manrope, sans-serif' }}>
      {/* Header */}
      <header style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 120, background: '#042C53', borderBottom: '1px solid #0C447C', padding: '12px 28px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.18em', color: '#85B7EB', fontWeight: 900 }}>Smart Exam System</div>
          <div style={{ fontSize: 16, fontWeight: 800, color: '#fff' }}>{exam?.exam_title || 'Exam'}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 10, color: '#85B7EB', textTransform: 'uppercase', letterSpacing: '0.18em' }}>Time Remaining</div>
            <div style={{ fontSize: 22, fontWeight: 900, color: timerColor, fontFamily: 'Courier New, monospace' }}>{timeLeft !== null ? formatTime(timeLeft) : '--:--'}</div>
          </div>
          <button onClick={() => handleSubmit(false)} disabled={submitting}
            style={{ background: '#1D9E75', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 18px', fontWeight: 800, fontSize: 13, cursor: 'pointer' }}>
            {submitting ? 'Submitting...' : 'Submit Exam'}
          </button>
        </div>
      </header>

      <div style={{ maxWidth: 860, margin: '0 auto', padding: '100px 1.25rem 120px' }}>
        {/* Progress */}
        <div style={{ background: '#fff', borderRadius: 10, padding: '0.75rem 1rem', marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: '1px solid #B5D4F4' }}>
          <span style={{ fontSize: 13, color: '#185FA5', fontWeight: 700 }}>Question {current + 1} of {questions.length}</span>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {questions.map((_, i) => (
              <button key={i} onClick={() => setCurrent(i)} style={{
                width: 28, height: 28, borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 700,
                background: i === current ? '#185FA5' : answers[questions[i]?.question_id || questions[i]?.id] ? '#1D9E75' : '#E6F1FB',
                color: i === current || answers[questions[i]?.question_id || questions[i]?.id] ? '#fff' : '#185FA5'
              }}>{i + 1}</button>
            ))}
          </div>
        </div>

        {/* Question */}
        {q && (
          <div style={{ background: '#fff', borderRadius: 14, padding: '1.5rem', border: '1px solid #B5D4F4', boxShadow: '0 4px 16px rgba(24,95,165,0.08)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
              <span style={{ background: '#E6F1FB', color: '#185FA5', padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 700 }}>Q{current + 1}</span>
              <span style={{ color: '#185FA5', fontSize: 12, fontWeight: 700 }}>{q.marks || 1} mark{q.marks !== 1 ? 's' : ''}</span>
            </div>
            <p style={{ fontSize: 16, fontWeight: 600, color: '#042C53', lineHeight: 1.6, marginBottom: 20 }}>{q.question_text || q.question}</p>

            {/* MCQ */}
            {(q.question_type === 'mcq' || q.type === 'mcq') && q.options && (
              <div style={{ display: 'grid', gap: 10 }}>
                {Object.entries(typeof q.options === 'object' && !Array.isArray(q.options) ? q.options : {}).map(([key, val]) => {
                  const qId = q.question_id || q.id
                  const selected = answers[qId] === key
                  return (
                    <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', borderRadius: 10, border: `1px solid ${selected ? '#185FA5' : '#B5D4F4'}`, background: selected ? '#E6F1FB' : '#F8FAFC', cursor: 'pointer' }}>
                      <input type="radio" name={`q_${qId}`} value={key} checked={selected} onChange={() => setAnswer(qId, key)} style={{ accentColor: '#185FA5' }} />
                      <span style={{ fontWeight: 600, color: '#185FA5', minWidth: 20 }}>{key}.</span>
                      <span style={{ color: '#042C53', fontSize: 14 }}>{val}</span>
                    </label>
                  )
                })}
              </div>
            )}

            {/* True/False */}
            {(q.question_type === 'true_false' || q.type === 'true_false') && (
              <div style={{ display: 'flex', gap: 12 }}>
                {['True', 'False'].map(opt => {
                  const qId = q.question_id || q.id
                  const selected = answers[qId] === opt
                  return (
                    <label key={opt} style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '12px', borderRadius: 10, border: `1px solid ${selected ? '#185FA5' : '#B5D4F4'}`, background: selected ? '#E6F1FB' : '#F8FAFC', cursor: 'pointer', fontWeight: 700, color: selected ? '#185FA5' : '#042C53' }}>
                      <input type="radio" name={`q_${qId}`} value={opt} checked={selected} onChange={() => setAnswer(qId, opt)} style={{ accentColor: '#185FA5' }} />
                      {opt}
                    </label>
                  )
                })}
              </div>
            )}

            {/* Essay / Short */}
            {!['mcq', 'true_false'].includes(q.question_type || q.type) && (
              <textarea
                value={answers[q.question_id || q.id] || ''}
                onChange={e => setAnswer(q.question_id || q.id, e.target.value)}
                placeholder="Write your answer here..."
                rows={5}
                style={{ width: '100%', border: '1px solid #B5D4F4', borderRadius: 10, padding: '12px', fontSize: 14, fontFamily: 'Manrope, sans-serif', resize: 'vertical', outline: 'none', background: '#F8FAFC', boxSizing: 'border-box' }}
              />
            )}
          </div>
        )}

        {/* Navigation */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
          <button onClick={() => setCurrent(c => Math.max(0, c - 1))} disabled={current === 0}
            style={{ background: current === 0 ? '#E6F1FB' : '#fff', border: '1px solid #B5D4F4', borderRadius: 8, padding: '10px 20px', fontWeight: 700, fontSize: 13, cursor: current === 0 ? 'not-allowed' : 'pointer', color: '#185FA5' }}>
            Previous
          </button>
          {current < questions.length - 1 ? (
            <button onClick={() => setCurrent(c => c + 1)}
              style={{ background: '#185FA5', color: '#fff', border: 'none', borderRadius: 8, padding: '10px 20px', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>
              Next
            </button>
          ) : (
            <button onClick={() => handleSubmit(false)} disabled={submitting}
              style={{ background: '#1D9E75', color: '#fff', border: 'none', borderRadius: 8, padding: '10px 20px', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>
              {submitting ? 'Submitting...' : 'Submit Exam'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
