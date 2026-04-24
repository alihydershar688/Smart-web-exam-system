// Authentication Check for Protected Pages
function checkAuth() {
    const isLoggedIn = sessionStorage.getItem('isLoggedIn');
    const userRole = sessionStorage.getItem('userRole');
    
    if (!isLoggedIn) {
        [
            'isLoggedIn', 'userRole', 'userEmail', 'userId', 'userName',
            'userFirstName', 'userLastName', 'studentId', 'teacherId', 'adminId',
            'userDepartment', 'userPhone', 'userAddress', 'userBio', 'userBatch',
            'authLoginAt', 'authLastActivityAt'
        ].forEach(key => localStorage.removeItem(key));
        // Redirect to login page with return URL
        const currentPage = window.location.pathname.split('/').pop();
        window.location.href = `login.html?return=${currentPage}`;
        return false;
    }
    
    return { isLoggedIn: true, role: userRole };
}

// Function to handle protected actions
function handleProtectedAction(action, requiredRole = null) {
    const auth = checkAuth();
    
    if (!auth || !auth.isLoggedIn) {
        return false;
    }
    
    if (requiredRole && auth.role !== requiredRole) {
        alert(`This action requires ${requiredRole} privileges.`);
        return false;
    }
    
    return true;
}

// Login function (to be called from login page)
function loginUser(email, password, role) {
    throw new Error('loginUser helper is deprecated. Use the real login flow in login.html.');
}

// Logout function
function logoutUser() {
    [
        'isLoggedIn', 'userRole', 'userEmail', 'userId', 'userName',
        'userFirstName', 'userLastName', 'studentId', 'teacherId', 'adminId',
        'userDepartment', 'userPhone', 'userAddress', 'userBio', 'userBatch',
        'authLoginAt', 'authLastActivityAt', 'authLogoutAt'
    ].forEach(key => {
        localStorage.removeItem(key);
        sessionStorage.removeItem(key);
    });
    window.location.href = 'index.html';
}

// Check current page protection
document.addEventListener('DOMContentLoaded', function() {
    const protectedPages = ['create-exam.html', 'dashboard-teacher.html', 'dashboard-admin.html', 'analytics.html'];
    const currentPage = window.location.pathname.split('/').pop();
    
    if (protectedPages.includes(currentPage)) {
        const auth = checkAuth();
        if (!auth.isLoggedIn) {
            return; // Redirect will happen in checkAuth()
        }
        
        // Update UI based on user role
        updateUIForUser(auth.role);
    }
});

function updateUIForUser(role) {
    // Update navigation based on role
    const userMenu = document.querySelector('.user-menu');
    if (userMenu) {
        const userEmail = sessionStorage.getItem('userEmail');
        userMenu.querySelector('span').textContent = `${userEmail} (${role})`;
    }
    
    // Show/hide elements based on role
    if (role === 'student') {
        const teacherElements = document.querySelectorAll('.teacher-only, .admin-only');
        teacherElements.forEach(el => el.style.display = 'none');
    } else if (role === 'teacher') {
        const adminElements = document.querySelectorAll('.admin-only');
        adminElements.forEach(el => el.style.display = 'none');
    }
}
