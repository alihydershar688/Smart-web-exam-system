import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ToastContainer } from './components/Toast'
import ProtectedRoute from './components/ProtectedRoute'

// Public
import Landing from './pages/Landing'
import Login from './pages/Login'
import Signup from './pages/Signup'

// Student
import StudentDashboard from './pages/student/StudentDashboard'
import TakeExam from './pages/student/TakeExam'
import ExamResults from './pages/student/ExamResults'

// Teacher
import TeacherDashboard from './pages/teacher/TeacherDashboard'
import CreateExam from './pages/teacher/CreateExam'

// Admin
import AdminDashboard from './pages/admin/AdminDashboard'
import ManageUsers from './pages/admin/ManageUsers'

function RootRedirect() {
  const { user, profile, loading } = useAuth()
  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#F0F4FF', fontFamily: 'Manrope, sans-serif' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ width: 40, height: 40, border: '3px solid rgba(30,58,138,0.15)', borderTop: '3px solid #1E3A8A', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 12px' }} />
        <p style={{ color: '#6B7280', fontSize: 14 }}>Loading...</p>
      </div>
    </div>
  )
  if (!user || !profile) return <Navigate to="/" replace />
  const map = { student: '/student', teacher: '/teacher', admin: '/admin', super_admin: '/admin' }
  return <Navigate to={map[profile.role] || '/'} replace />
}

function Guard({ roles, children }) {
  return <ProtectedRoute allowedRoles={roles}>{children}</ProtectedRoute>
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ToastContainer />
        <Routes>
          {/* Public */}
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/dashboard" element={<RootRedirect />} />

          {/* Student */}
          <Route path="/student" element={<Guard roles={['student']}><StudentDashboard /></Guard>} />
          <Route path="/student/exams" element={<Guard roles={['student']}><StudentDashboard /></Guard>} />
          <Route path="/student/take-exam" element={<Guard roles={['student']}><TakeExam /></Guard>} />
          <Route path="/student/results" element={<Guard roles={['student']}><ExamResults /></Guard>} />

          {/* Teacher */}
          <Route path="/teacher" element={<Guard roles={['teacher']}><TeacherDashboard /></Guard>} />
          <Route path="/teacher/create-exam" element={<Guard roles={['teacher']}><CreateExam /></Guard>} />

          {/* Admin + Super Admin */}
          <Route path="/admin" element={<Guard roles={['admin', 'super_admin']}><AdminDashboard /></Guard>} />
          <Route path="/admin/users" element={<Guard roles={['admin', 'super_admin']}><ManageUsers /></Guard>} />

          {/* Catch all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
