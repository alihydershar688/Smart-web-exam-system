/**
 * EXAM SYSTEM - FRONTEND UTILITIES
 * Common helper functions for all dashboards
 * Save this as: frontend/js/exam-utils.js
 */

class ExamSystemAPI {
    constructor(supabaseClient) {
        this.supabase = supabaseClient;
        this.baseUrl = window.AppConfig.getBackendBase();
    }

    /**
     * Build headers for authenticated API calls
     */
    async _buildHeaders(additionalHeaders = {}) {
        return window.AppConfig.buildAuthHeaders(this.supabase, {
            'Content-Type': 'application/json',
            ...additionalHeaders
        });
    }

    /**
     * Generic fetch wrapper
     */
    async _apiCall(endpoint, options = {}) {
        const headers = await this._buildHeaders(options.headers);
        const response = await fetch(`${this.baseUrl}${endpoint}`, {
            ...options,
            headers
        });
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || `API Error: ${response.status}`);
        }
        return data;
    }

    // ================== COURSE ENDPOINTS ==================

    /**
     * Get all courses for logged-in user
     */
    async getUserCourses() {
        return this._apiCall('/exams/courses');
    }

    /**
     * Get exams in a specific course
     */
    async getCourseExams(courseId) {
        return this._apiCall(`/exams/by-course/${courseId}`);
    }

    // ================== EXAM ENDPOINTS ==================

    /**
     * Generate exam from uploaded materials
     * @param {Object} params - { course_id, exam_title, materials, num_questions, question_types, difficulty }
     */
    async generateExam(params) {
        return this._apiCall('/exams/generate', {
            method: 'POST',
            body: JSON.stringify(params)
        });
    }

    /**
     * Get exam details including questions
     */
    async getExamDetail(examId) {
        return this._apiCall(`/exams/${examId}`);
    }

    /**
     * Publish an exam (make visible to students)
     */
    async publishExam(examId) {
        return this._apiCall(`/exams/${examId}/publish`, {
            method: 'POST'
        });
    }

    // ================== EXAM ATTEMPT ENDPOINTS ==================

    /**
     * Start a new exam attempt
     */
    async startExamAttempt(examId) {
        return this._apiCall('/exams/attempts/start', {
            method: 'POST',
            body: JSON.stringify({ exam_id: examId })
        });
    }

    /**
     * Submit completed exam
     */
    async submitExamAttempt(attemptId, answers) {
        return this._apiCall(`/exams/attempts/${attemptId}/submit`, {
            method: 'POST',
            body: JSON.stringify({ answers })
        });
    }

    /**
     * Get attempt details (for viewing/grading)
     */
    async getAttemptDetail(attemptId) {
        return this._apiCall(`/exams/attempts/${attemptId}`);
    }

    /**
     * Update marks for an attempt (Teacher only)
     */
    async updateAttemptMarks(attemptId, marks, comments = '') {
        return this._apiCall(`/exams/attempts/${attemptId}/marks`, {
            method: 'PUT',
            body: JSON.stringify({
                manual_marks: marks,
                comments: comments
            })
        });
    }
}

// ===============================================================
// UI HELPER FUNCTIONS
// ===============================================================

/**
 * Format a date for display
 */
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

/**
 * Format percentage for display
 */
function formatPercentage(percentage) {
    if (percentage === null || percentage === undefined) return '-';
    return Math.round(percentage) + '%';
}

/**
 * Convert percentage to letter grade
 */
function getLetterGrade(percentage) {
    if (percentage === null || percentage === undefined) return '-';
    if (percentage >= 90) return 'A';
    if (percentage >= 80) return 'B';
    if (percentage >= 70) return 'C';
    if (percentage >= 60) return 'D';
    return 'F';
}

/**
 * Get color for grade
 */
function getGradeColor(percentage) {
    if (percentage >= 90) return '#10b981'; // Green - A
    if (percentage >= 80) return '#3b82f6'; // Blue - B
    if (percentage >= 70) return '#f59e0b'; // Amber - C
    if (percentage >= 60) return '#ef4444'; // Red - D
    return '#7c3aed'; // Purple - F
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Remove existing toast
    const existing = document.querySelector('.toast-notification');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 12px 24px;
        border-radius: 8px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
        color: white;
        z-index: 9999;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * Show loading spinner
 */
function showLoading(message = 'Loading...') {
    const spinner = document.createElement('div');
    spinner.id = 'loading-spinner';
    spinner.innerHTML = `
        <div style="
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9998;
        ">
            <div style="
                background: white;
                padding: 30px;
                border-radius: 12px;
                text-align: center;
            ">
                <div style="
                    width: 40px;
                    height: 40px;
                    border: 4px solid #3b82f6;
                    border-top-color: transparent;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin: 0 auto 15px;
                "></div>
                <p style="margin: 0; color: #333; font-weight: 500;">${message}</p>
            </div>
        </div>
    `;
    document.body.appendChild(spinner);
}

/**
 * Hide loading spinner
 */
function hideLoading() {
    const spinner = document.getElementById('loading-spinner');
    if (spinner) spinner.remove();
}

/**
 * Validate email
 */
function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/**
 * Validate exam title
 */
function isValidExamTitle(title) {
    return title && title.trim().length >= 3 && title.trim().length <= 255;
}

/**
 * Count words in text
 */
function countWords(text) {
    return text.trim().split(/\s+/).filter(word => word.length > 0).length;
}

/**
 * Convert minutes to readable format
 */
function formatDuration(minutes) {
    if (minutes < 1) return '< 1 min';
    if (minutes < 60) return minutes + ' min';
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}h ${mins}m`;
}

/**
 * Time remaining for timed exam
 */
function getRemainingTime(startTime, durationMinutes) {
    const elapsed = (Date.now() - new Date(startTime).getTime()) / 1000 / 60;
    const remaining = durationMinutes - elapsed;
    if (remaining <= 0) return null;
    return Math.floor(remaining);
}

/**
 * Format seconds to MM:SS
 */
function formatTimer(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

/**
 * Get exam status badge color
 */
function getStatusColor(status) {
    const colors = {
        'draft': '#94a3b8',      // Gray
        'published': '#10b981',   // Green
        'archived': '#6b7280',    // Dark Gray
        'in_progress': '#3b82f6', // Blue
        'submitted': '#f59e0b',   // Amber
        'graded': '#8b5cf6'       // Purple
    };
    return colors[status] || '#6b7280';
}

/**
 * Convert object to CSV download
 */
function downloadAsCSV(data, filename = 'export.csv') {
    const headers = Object.keys(data[0] || {});
    const csv = [
        headers.join(','),
        ...data.map(row => 
            headers.map(header => {
                const value = row[header];
                // Escape quotes and wrap in quotes if contains comma
                if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
                    return `"${value.replace(/"/g, '""')}"`;
                }
                return value;
            }).join(',')
        )
    ].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    window.URL.revokeObjectURL(url);
}

/**
 * Check if current user has permission for action
 */
function checkPermission(action, userRole) {
    const permissions = {
        'create_exam': ['teacher', 'admin'],
        'publish_exam': ['teacher', 'admin'],
        'grade_exam': ['teacher', 'admin'],
        'take_exam': ['student'],
        'manage_users': ['admin'],
        'manage_courses': ['admin', 'teacher'],
        'view_analytics': ['admin', 'teacher']
    };
    
    return (permissions[action] || []).includes(userRole);
}

/**
 * Get user role display name
 */
function getRoleDisplayName(role) {
    const names = {
        'admin': 'Administrator',
        'teacher': 'Teacher',
        'student': 'Student'
    };
    return names[role] || role;
}

/**
 * Add CSS animation styles
 */
function injectAnimationStyles() {
    if (document.getElementById('exam-system-animations')) return;
    
    const style = document.createElement('style');
    style.id = 'exam-system-animations';
    style.textContent = `
        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        @keyframes slideIn {
            from { transform: translateY(100px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateY(0); opacity: 1; }
            to { transform: translateY(100px); opacity: 0; }
        }
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        .toast-notification {
            animation: slideIn 0.3s ease;
        }
    `;
    document.head.appendChild(style);
}

// Initialize animations on load
document.addEventListener('DOMContentLoaded', injectAnimationStyles);

// Export for use in scripts
window.ExamSystemAPI = ExamSystemAPI;
window.showToast = showToast;
window.showLoading = showLoading;
window.hideLoading = hideLoading;
window.formatDate = formatDate;
window.formatPercentage = formatPercentage;
window.getLetterGrade = getLetterGrade;
window.formatDuration = formatDuration;
