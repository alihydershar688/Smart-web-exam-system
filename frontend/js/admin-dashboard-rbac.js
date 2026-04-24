/**
 * Admin Dashboard RBAC Integration
 * Uses Supabase directly for reliable stats loading.
 */

async function initAdminDashboard() {
    try {
        const userRole = localStorage.getItem('userRole')
        if (userRole !== 'admin') return
        await loadAdminStats()
    } catch (error) {
        console.error('Admin Dashboard Init Error:', error)
    }
}

async function loadAdminStats() {
    // Use Supabase client directly — more reliable than the RBAC API endpoint
    if (!window.supabaseClient && !window.db) return

    const client = window.supabaseClient || window.db
    try {
        const [usersRes, examsRes, coursesRes, attemptsRes] = await Promise.all([
            client.from('users').select('id, role, status'),
            client.from('exams').select('exam_id, status').eq('status', 'published'),
            client.from('courses').select('id'),
            client.from('exam_attempts').select('attempt_id, status').in('status', ['submitted', 'pending_grading'])
        ])

        const users = usersRes.data || []
        const exams = examsRes.data || []
        const courses = coursesRes.data || []
        const pending = attemptsRes.data || []

        const roleCount = users.reduce((acc, u) => {
            acc[u.role] = (acc[u.role] || 0) + 1
            return acc
        }, {})

        // Update stat cards
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val }
        set('totalUsers',   users.length)
        set('activeExams',  exams.length)
        set('totalCourses', courses.length)
        set('userBreakdown', `Teachers: ${roleCount.teacher || 0} | Students: ${roleCount.student || 0} | Admins: ${roleCount.admin || 0}`)

        // Load recent users into the recentUsers container
        const container = document.getElementById('recentUsers')
        if (container && users.length > 0) {
            const recent = [...users].sort((a, b) => 0).slice(0, 5)
            const table = document.createElement('table')
            table.className = 'users-table'
            table.innerHTML = `
                <thead><tr>
                    <th>Email</th><th>Role</th><th>Status</th>
                </tr></thead>
                <tbody>
                    ${recent.map(u => `
                        <tr>
                            <td>${escapeHtml(u.email || 'N/A')}</td>
                            <td><span class="badge badge-${u.role || 'student'}">${(u.role || 'student').toUpperCase()}</span></td>
                            <td><span class="badge badge-${u.status === 'active' ? 'active' : 'suspended'}">${u.status || 'unknown'}</span></td>
                        </tr>
                    `).join('')}
                </tbody>
            `
            container.innerHTML = ''
            container.appendChild(table)
        }

    } catch (error) {
        console.error('Error loading admin stats:', error)
    }
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
}
