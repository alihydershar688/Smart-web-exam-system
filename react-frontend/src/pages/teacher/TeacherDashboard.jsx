import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import DashboardLayout from '../../components/DashboardLayout'
import StatCard from '../../components/StatCard'
import Spinner from '../../components/Spinner'
import { useAuth } from '../../context/AuthContext'
import { apiRequest } from '../../utils/api'

const NAV = [
  { to: '/teacher', icon: '⊞', label: 'Dashboard' },
  { to: '/teacher/create-exam', icon: '✚', label: 'Create Exam' },
  { to: '/teacher/submissions', icon: '📋', label: 'Submissions' },
  { to: '/teacher/results', icon: '🏆', label: 'Results' },
  { to: '/teacher/students', icon: '👥', label: 'Students' },
  { to: '/teacher/analytics', icon: '📊', label: 'Analytics' },
]

export default function TeacherDashboard() {
  const { profile } = useAuth()
  const navigate = useNavigate()
  const [stats, setStats] = useState({})
  const [exams, setExams] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadData() }, [])

  async function loadData() {
    setLoading(true)
    try {
      const res = await apiRequest('/exams?status=published,draft,archived')
      const allExams = res.data?.exams || []
      setExams(allExams.slice(0, 8))
      setStats({
        total: allExams.length,
        active: allExams.filter(e => e.status === 'published').length,
      })
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const statusColor = { published: '#1E3A8A', draft: '#F59E0B', archived: '#6B7280' }
  const statusBg = { published: '#DBEAFE', draft: '#FEF3C7', archived: '#F3F4F6' }

  return (
    <DashboardLayout navLinks={NAV} title="Teacher Dashboard">
      <div style={{ marginBottom: '1.2rem', background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10, padding: '1rem 1.2rem', boxShadow: '0 2px 8px rgba(30,58,138,0.07)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#1E3A8A', margin: 0 }}>Welcome back, {profile?.first_name || 'Teacher'}!</h1>
          <p style={{ color: '#6B7280', fontSize: 13, margin: '4px 0 0' }}>Manage your exams, grade submissions, and track student performance.</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => navigate('/teacher/create-exam')} style={{ background: '#1E3A8A', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 16px', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>Create New Exam</button>
        </div>
      </div>

      {loading ? <div style={{ textAlign: 'center', padding: '3rem' }}><Spinner /></div> : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: '1.2rem' }}>
            <StatCard label="Total Exams" value={stats.total ?? 0} footer="All time" accent="#2563EB" />
            <StatCard label="Active Exams" value={stats.active ?? 0} footer="Currently published" accent="#10b981" />
          </div>

          <div style={{ background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10, padding: '1rem', boxShadow: '0 2px 8px rgba(30,58,138,0.07)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', paddingBottom: '0.75rem', borderBottom: '1px solid #DBEAFE' }}>
              <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: '#1E3A8A' }}>Recent Exams</h3>
            </div>
            {exams.length === 0 ? (
              <p style={{ color: '#6B7280', textAlign: 'center', padding: '2rem', fontSize: 14 }}>No exams yet. Create your first exam!</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 500 }}>
                  <thead>
                    <tr style={{ background: '#1E3A8A' }}>
                      {['Exam Name', 'Status', 'Submissions', 'Actions'].map(h => (
                        <th key={h} style={{ padding: '0.65rem 0.85rem', textAlign: 'left', color: '#fff', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {exams.map((exam, i) => (
                      <tr key={exam.exam_id || i} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFC', borderBottom: '1px solid #E0E7FF' }}>
                        <td style={{ padding: '0.65rem 0.85rem', color: '#1F2937', fontWeight: 600, fontSize: 13 }}>{exam.exam_title || 'Untitled'}</td>
                        <td style={{ padding: '0.65rem 0.85rem' }}>
                          <span style={{ background: statusBg[exam.status] || '#F3F4F6', color: statusColor[exam.status] || '#6B7280', padding: '3px 10px', borderRadius: 999, fontSize: 12, fontWeight: 700 }}>
                            {exam.status}
                          </span>
                        </td>
                        <td style={{ padding: '0.65rem 0.85rem', color: '#6B7280', fontSize: 13 }}>0</td>
                        <td style={{ padding: '0.65rem 0.85rem' }}>
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            <button onClick={() => navigate(`/teacher/view-exam?id=${exam.exam_id}`)}
                              style={{ background: '#EFF6FF', border: '1px solid #BFDBFE', color: '#1E3A8A', borderRadius: 6, padding: '4px 10px', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>View</button>
                            {exam.status === 'draft' && (
                              <button style={{ background: '#1E3A8A', color: '#fff', border: 'none', borderRadius: 6, padding: '4px 10px', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>Publish</button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </DashboardLayout>
  )
}
