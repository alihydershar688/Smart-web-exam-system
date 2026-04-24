"""
RBAC Middleware and Authorization Utilities
"""
from functools import wraps
from flask import request, jsonify, g
import json


class PermissionDenied(Exception):
    def __init__(self, message="Permission denied"):
        self.message = message
        super().__init__(self.message)


def require_role(*roles):
    """Decorator to require specific roles"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = request.headers.get('X-User-Role', '').lower()
            if user_role not in [r.lower() for r in roles]:
                return jsonify({
                    'success': False,
                    'error': f'This action requires one of: {", ".join(roles)}'
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = request.headers.get('X-User-ID')
        user_email = request.headers.get('X-User-Email')
        user_role = request.headers.get('X-User-Role')
        
        if not all([user_id, user_email, user_role]):
            return jsonify({
                'success': False,
                'error': 'Authentication required'
            }), 401
        
        g.user = {
            'id': user_id,
            'email': user_email,
            'role': user_role.lower()
        }
        return f(*args, **kwargs)
    return decorated_function


def verify_course_access(supabase_client, user_id, course_id):
    """
    Verify that user has access to a course.
    Checks the primary 'enrollments' table (student_id + course_id).
    Falls back to 'course_enrollments' legacy table via course_code lookup.
    Returns: True if access granted, False otherwise
    """
    try:
        # Primary: enrollments table (student_id + course_id)
        result = supabase_client.table('enrollments').select(
            'enrollment_id'
        ).eq('student_id', user_id).eq('course_id', course_id).execute()
        if result.data and len(result.data) > 0:
            return True
    except Exception as e:
        print(f"Course access verification (enrollments) failed: {e}")

    try:
        # Fallback: course_enrollments uses course_code not course_id
        # Look up course_code from courses table first
        course_resp = supabase_client.table('courses').select('course_code').eq('id', course_id).limit(1).execute()
        if course_resp.data:
            course_code = course_resp.data[0].get('course_code')
            if course_code:
                result2 = supabase_client.table('course_enrollments').select(
                    'enrollment_id'
                ).eq('user_id', user_id).eq('course_code', course_code).execute()
                return len(result2.data) > 0 if result2.data else False
    except Exception as e:
        print(f"Course access verification (course_enrollments) failed: {e}")

    return False


def verify_exam_access(supabase_client, user_id, exam_id, user_role):
    """
    Verify that user can access an exam based on:
    - If teacher: created the exam
    - If student: enrolled in course that exam is assigned to
    """
    try:
        # Get exam details
        exam_result = supabase_client.table('exams').select(
            'exam_id, teacher_id, course_id, status'
        ).eq('exam_id', exam_id).execute()
        
        if not exam_result.data or len(exam_result.data) == 0:
            return False
        
        exam = exam_result.data[0]
        
        # Teacher can access own exams
        if user_role.lower() == 'teacher':
            return exam.get('teacher_id') == user_id
        
        # Student can access published exams in enrolled courses
        if user_role.lower() == 'student':
            if exam.get('status') != 'published':
                return False
            
            course_id = exam.get('course_id')
            if not course_id:
                return False
            
            return verify_course_access(supabase_client, user_id, course_id)
        
        return False
    except Exception as e:
        print(f"Exam access verification failed: {e}")
        return False


def get_user_courses(supabase_client, user_id, role=None):
    """Get all course codes a user is enrolled in"""
    try:
        query = supabase_client.table('course_enrollments').select(
            'course_code, enrollment_role'
        ).eq('user_id', user_id).eq('enrollment_status', 'active')
        
        if role:
            query = query.eq('enrollment_role', role)
        
        result = query.execute()
        courses = []
        if result.data:
            for enrollment in result.data:
                courses.append({
                    'course_code': enrollment.get('course_code'),
                    'enrollment_role': enrollment.get('enrollment_role')
                })
        return courses
    except Exception as e:
        print(f"Failed to get user courses: {e}")
        return []


def get_course_exams(supabase_client, course_code_or_id, status=None):
    """Get exams for a course (accepts course_code and converts to course_id)"""
    try:
        # First, get the course_id from course_code
        course_id = None
        
        # Try to look up course_code -> course_id
        try:
            result = supabase_client.table('courses').select('id').eq(
                'course_code', course_code_or_id
            ).limit(1).execute()
            
            if result.data:
                course_id = result.data[0]['id']
        except Exception:
            # If course_code lookup fails, assume it's already a course_id
            course_id = course_code_or_id
        
        if not course_id:
            return []
        
        # Query exams by course_id
        query = supabase_client.table('exams').select(
            'exam_id, exam_title, course_id, duration_minutes, total_marks, status, description, created_at, updated_at'
        ).eq('course_id', course_id)
        
        if status:
            query = query.eq('status', status)
        
        result = query.execute()
        exams = []
        if result.data:
            for exam in result.data:
                exams.append({
                    'exam_id': exam.get('exam_id'),
                    'exam_title': exam.get('exam_title'),
                    'course_id': exam.get('course_id'),
                    'duration_minutes': exam.get('duration_minutes'),
                    'total_marks': exam.get('total_marks'),
                    'status': exam.get('status'),
                    'description': exam.get('description'),
                    'created_at': exam.get('created_at'),
                    'updated_at': exam.get('updated_at'),
                })
        return exams
    except Exception as e:
        print(f"Failed to get course exams: {e}")
        return []


def extract_user_from_auth_header():
    """Extract user info from authorization headers"""
    try:
        return {
            'id': request.headers.get('X-User-ID'),
            'email': request.headers.get('X-User-Email'),
            'role': request.headers.get('X-User-Role', 'student').lower()
        }
    except:
        return None
