import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import DashboardLayout from '../../components/DashboardLayout'
import StatCard from '../../components/StatCard'
import Spinner from '../../components/Spinner'
import { useAuth } from '../../context/AuthContext'
import { apiRequest } from '../../utils/api'

const NAV = [
  { to: '/student', icon: '⊞', label: 'Dashboard' },
  { to: '/student/exams', icon: '📋', label: 'Available Exams' },
  { to: '/student/results', icon: '📊', label: 'My Results' },
  { to: '/student/profile', icon: '👤', label: 'Profile' },
]

export default function StudentDashboard() {
  const { profile } = useAuth()
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [exams, setExams] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    try {
      const [coursesRes, examsRes] = await Promise.all([
        apiRequest('/student/courses'),
        apiRequest('/exams?status=published'),
      ])
      const courses = coursesRes.data?.courses || []
      const availableExams = examsRes.data?.exams || []
      setExams(availableExams.slice(0, 5))
      setStats({ courses: courses.length, exams: availableExams.length })
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <DashboardLayout navLinks={NAV} title="Student Dashboard">
      <div style={{ marginBottom: '1.2rem', background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10, padding: '1rem 1.2rem', boxShadow: '0 2px 8px rgba(30,58,138,0.07)' }}>
        <h1 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#1E3A8A', margin: 0 }}>
          Welcome back, {profile?.first_name || 'Student'}!
        </h1>
        <p style={{ color: '#6B7280', fontSize: 13, margin: '4px 0 0' }}>View your exams, results, and performance.</p>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem' }}><Spinner /></div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: '1.2rem' }}>
            <StatCard label="Enrolled Courses" value={stats?.courses ?? 0} footer="Active enrollments" accent="#2563EB" />
            <StatCard label="Available Exams" value={stats?.exams ?? 0} footer="Ready to attempt" accent="#10b981" onClick={() => navigate('/student/exams')} />
          </div>

          <div style={{ background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10, padding: '1rem', boxShadow: '0 2px 8px rgba(30,58,138,0.07)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', paddingBottom: '0.75rem', borderBottom: '1px solid #DBEAFE' }}>
              <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: '#1E3A8A' }}>Available Exams</h3>
              <button onClick={() => navigate('/student/exams')} style={{ background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: 8, padding: '4px 12px', color: '#1E3A8A', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>View All</button>
            </div>
            {exams.length === 0 ? (
              <p style={{ color: '#6B7280', textAlign: 'center', padding: '2rem', fontSize: 14 }}>No exams available right now.</p>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#1E3A8A' }}>
                    {['Exam Title', 'Subject', 'Duration', 'Action'].map(h => (
                      <th key={h} style={{ padding: '0.7rem 0.9rem', textAlign: 'left', color: '#fff', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {exams.map((exam, i) => (
                    <tr key={exam.exam_id || i} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFC', borderBottom: '1px solid #E0E7FF' }}>
                      <td style={{ padding: '0.7rem 0.9rem', color: '#1F2937', fontWeight: 600, fontSize: 13 }}>{exam.exam_title || 'Exam'}</td>
                      <td style={{ padding: '0.7rem 0.9rem', color: '#6B7280', fontSize: 13 }}>{exam.subject || '—'}</td>
                      <td style={{ padding: '0.7rem 0.9rem', color: '#6B7280', fontSize: 13 }}>{exam.duration_minutes ? `${exam.duration_minutes} min` : '—'}</td>
                      <td style={{ padding: '0.7rem 0.9rem' }}>
                        <button onClick={() => navigate(`/student/take-exam?id=${exam.exam_id}`)}
                          style={{ background: '#1E3A8A', color: '#fff', border: 'none', borderRadius: 6, padding: '5px 14px', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
                          Start
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </DashboardLayout>
  )
}
