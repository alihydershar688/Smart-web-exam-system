// Signup Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    initializeSignupPage();
});

function initializeSignupPage() {
    // Role selection
    const roleCards = document.querySelectorAll('.role-card');
    const signupForm = document.getElementById('signupForm');
    const backToRole = document.getElementById('backToRole');
    
    roleCards.forEach(card => {
        card.addEventListener('click', function() {
            // Remove selected class from all cards
            roleCards.forEach(c => c.classList.remove('selected'));
            // Add selected class to clicked card
            this.classList.add('selected');
            
            const role = this.getAttribute('data-role');
            showRegistrationForm(role);
        });
    });

    // Password strength indicator
    const passwordInput = document.getElementById('password');
    if (passwordInput) {
        passwordInput.addEventListener('input', checkPasswordStrength);
    }

    // Password confirmation check
    const confirmPasswordInput = document.getElementById('confirmPassword');
    if (confirmPasswordInput) {
        confirmPasswordInput.addEventListener('input', checkPasswordMatch);
    }

    // Form submission
    const signupFormElement = document.getElementById('signupForm');
    if (signupFormElement) {
        signupFormElement.addEventListener('submit', handleSignup);
    }
}

function showRegistrationForm(role) {
    // Hide role selection
    document.querySelector('.role-selection').style.display = 'none';
    
    // Show registration form
    document.getElementById('signupForm').style.display = 'block';
    document.getElementById('backToRole').style.display = 'block';
    
    // Hide all role-specific fields first
    document.querySelectorAll('.role-specific-fields').forEach(field => {
        field.style.display = 'none';
    });
    
    // Show fields for selected role
    switch(role) {
        case 'student':
            document.getElementById('studentFields').style.display = 'block';
            updateFormForStudent();
            break;
        case 'teacher':
            document.getElementById('teacherFields').style.display = 'block';
            updateFormForTeacher();
            break;
        case 'admin':
            document.getElementById('adminFields').style.display = 'block';
            updateFormForAdmin();
            break;
    }
}

function showRoleSelection() {
    // Show role selection
    document.querySelector('.role-selection').style.display = 'block';
    
    // Hide registration form
    document.getElementById('signupForm').style.display = 'none';
    document.getElementById('backToRole').style.display = 'none';
    
    // Clear any selected role
    document.querySelectorAll('.role-card').forEach(card => {
        card.classList.remove('selected');
    });
}

function updateFormForStudent() {
    // Update form title or add student-specific logic
    document.querySelector('.auth-header h1').textContent = 'Student Registration';
    document.querySelector('.auth-header p').textContent = 'Create your student account to start taking exams';
}

function updateFormForTeacher() {
    document.querySelector('.auth-header h1').textContent = 'Teacher Registration';
    document.querySelector('.auth-header p').textContent = 'Create your teacher account to start creating exams';
}

function updateFormForAdmin() {
    document.querySelector('.auth-header h1').textContent = 'Administrator Registration';
    document.querySelector('.auth-header p').textContent = 'Create your administrator account for system management';
}

function checkPasswordStrength() {
    const password = this.value;
    const strengthBar = document.querySelector('.strength-bar');
    const strengthLabel = document.getElementById('strengthLabel');
    
    let strength = 0;
    let feedback = '';
    
    // Check password length
    if (password.length >= 8) strength += 25;
    if (password.length >= 12) strength += 25;
    
    // Check for mixed case
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength += 25;
    
    // Check for numbers and special characters
    if (/\d/.test(password)) strength += 15;
    if (/[^A-Za-z0-9]/.test(password)) strength += 10;
    
    // Update strength indicator
    if (strength < 50) {
        strengthBar.className = 'strength-bar weak';
        strengthLabel.textContent = 'Weak';
        strengthLabel.style.color = 'var(--warning)';
    } else if (strength < 75) {
        strengthBar.className = 'strength-bar medium';
        strengthLabel.textContent = 'Medium';
        strengthLabel.style.color = 'var(--secondary)';
    } else {
        strengthBar.className = 'strength-bar strong';
        strengthLabel.textContent = 'Strong';
        strengthLabel.style.color = 'var(--accent)';
    }
}

function checkPasswordMatch() {
    const password = document.getElementById('password').value;
    const confirmPassword = this.value;
    const passwordError = document.getElementById('passwordError');
    
    if (confirmPassword && password !== confirmPassword) {
        passwordError.style.display = 'block';
        this.style.borderColor = 'var(--warning)';
    } else {
        passwordError.style.display = 'none';
        this.style.borderColor = 'var(--border)';
    }
}

function handleSignup(e) {
    e.preventDefault();
    
    // Get form data
    const formData = {
        firstName: document.getElementById('firstName').value,
        lastName: document.getElementById('lastName').value,
        email: document.getElementById('email').value,
        password: document.getElementById('password').value,
        role: getSelectedRole(),
        newsletter: document.getElementById('newsletter').checked,
        terms: document.getElementById('terms').checked
    };
    
    // Add role-specific data
    switch(formData.role) {
        case 'student':
            formData.studentId = document.getElementById('studentId').value;
            formData.batch = document.getElementById('batch').value;
            formData.department = document.getElementById('department').value;
            break;
        case 'teacher':
            formData.teacherId = document.getElementById('teacherId').value;
            formData.department = document.getElementById('teacherDepartment').value;
            formData.courses = document.getElementById('courses').value;
            break;
        case 'admin':
            formData.adminId = document.getElementById('adminId').value;
            formData.accessLevel = document.getElementById('accessLevel').value;
            formData.termsAgreement = document.getElementById('termsAgreement').checked;
            break;
    }
    
    // Validate form
    if (!validateForm(formData)) {
        return;
    }
    
    // Show loading state
    const submitBtn = e.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.textContent;
    submitBtn.textContent = 'Creating Account...';
    submitBtn.disabled = true;
    
    // Simulate API call
    simulateSignup(formData)
        .then(response => {
            showSuccessMessage(formData);
        })
        .catch(error => {
            showError(error.message);
            submitBtn.textContent = originalText;
            submitBtn.disabled = false;
        });
}

function getSelectedRole() {
    const selectedCard = document.querySelector('.role-card.selected');
    return selectedCard ? selectedCard.getAttribute('data-role') : null;
}

function validateForm(formData) {
    // Basic validation
    if (!formData.firstName || !formData.lastName) {
        showError('Please enter your full name');
        return false;
    }
    
    if (!formData.email || !isValidEmail(formData.email)) {
        showError('Please enter a valid university email address');
        return false;
    }
    
    if (!formData.password || formData.password.length < 8) {
        showError('Password must be at least 8 characters long');
        return false;
    }
    
    if (formData.password !== document.getElementById('confirmPassword').value) {
        showError('Passwords do not match');
        return false;
    }
    
    if (!formData.terms) {
        showError('Please agree to the Terms of Service and Privacy Policy');
        return false;
    }
    
    // Role-specific validation
    switch(formData.role) {
        case 'student':
            if (!formData.studentId) {
                showError('Please enter your Student ID');
                return false;
            }
            if (!formData.department) {
                showError('Please select your department');
                return false;
            }
            break;
        case 'teacher':
            if (!formData.teacherId) {
                showError('Please enter your Teacher ID');
                return false;
            }
            if (!formData.department) {
                showError('Please select your department');
                return false;
            }
            break;
        case 'admin':
            if (!formData.adminId) {
                showError('Please enter your Admin ID');
                return false;
            }
            if (!formData.accessLevel) {
                showError('Please select an access level');
                return false;
            }
            if (!formData.termsAgreement) {
                showError('Please agree to the administrator terms');
                return false;
            }
            break;
    }
    
    return true;
}

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

function simulateSignup(formData) {
    return new Promise((resolve, reject) => {
        setTimeout(() => {
            if (Math.random() > 0.1) {
                resolve({ success: true });
            } else {
                reject(new Error('Registration failed. Please try again.'));
            }
        }, 1500);
    });
}

function showSuccessMessage(formData) {
    const authCard = document.querySelector('.auth-card');
    authCard.innerHTML = `
        <div class="success-message">
            <div class="success-icon">✅</div>
            <h2>Account Created Successfully!</h2>
            <p>Welcome ${formData.firstName}! Your ${formData.role} account has been created.</p>
            <p>Please check your email for verification.</p>
            <a href="login.html" class="btn btn-primary" style="margin-top: 1.5rem;">Go to Login</a>
        </div>
    `;
}

function showError(message) {
    const errorElement = document.getElementById('formError');
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.display = 'block';
    } else {
        alert(message);
    }
}
