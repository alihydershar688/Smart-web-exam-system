/**
 * Teacher Dashboard RBAC Integration
 * Fetches teacher's assigned courses and integrates with dashboard.
 * Note: Primary dashboard logic lives in dashboard-teacher.html inline scripts.
 * This module handles the /api/exams/teacher/courses-with-exams endpoint integration.
 */

async function initTeacherDashboard() {
    try {
        const userRole = localStorage.getItem('userRole')
        if (userRole !== 'teacher') return
        await loadTeacherCourses()
        await loadTeacherStats()
    } catch (error) {
        if (typeof showToast === 'function') showToast('Error loading teacher dashboard', 'error')
    }
}

async function loadTeacherCourses() {
    const backendBase = window.AppConfig?.getBackendBase?.() || 'http://127.0.0.1:5000/api'
    const apiUrl = (path) => {
        const cleanBase = String(backendBase || '').replace(/\/+$/, '')
        const cleanPath = String(path || '').replace(/^\/+/, '')
        return `${cleanBase}/${cleanPath}`
    }

    const readJsonSafely = async (response) => {
        const text = await response.text()
        if (!text) return null
        try {
            return JSON.parse(text)
        } catch (_) {
            const preview = text.trim().slice(0, 90)
            throw new Error(`Expected JSON from backend, received: ${preview}`)
        }
    }

    try {
        const headers = await window.AppConfig?.buildAuthHeaders?.(window.supabaseClient || null) || {
            'X-User-Email': localStorage.getItem('userEmail') || '',
            'X-User-ID': localStorage.getItem('userId') || '',
            'X-User-Role': 'teacher',
        }
        const response = await fetch(apiUrl('/teacher/courses'), {
            method: 'GET',
            headers,
        })
        const result = await readJsonSafely(response)
        if (!response.ok) {
            throw new Error(result?.error || result?.message || `HTTP ${response.status}`)
        }
        const courses = Array.isArray(result?.courses) ? result.courses : []
        if (!result?.success || !Array.isArray(courses)) {
            throw new Error('Invalid response format')
        }
        updateTeacherCourseSummary(courses)
    } catch (error) {
        console.warn('Teacher course summary unavailable:', error)
    }
}

function updateTeacherCourseSummary(courses) {
    const courseCount = Array.isArray(courses) ? courses.length : 0
    const sidebarMetaEl = document.getElementById('sidebarTeacherMeta')
    if (sidebarMetaEl && courseCount > 0) {
        sidebarMetaEl.textContent = `${courseCount} assigned course${courseCount !== 1 ? 's' : ''}`
    }
}

async function loadTeacherStats() {
    // Stats are populated from course data in updateTeacherStats()
}

function _escapeHtml(text) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
    return String(text || '').replace(/[&<>"']/g, m => map[m])
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTeacherDashboard)
} else {
    initTeacherDashboard()
}
