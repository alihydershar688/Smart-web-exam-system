"""
Exam Operations API Endpoints
- Generate exams from uploaded materials
- Submit student exam attempts  
Study Materials
- Auto-grade submissions
- Support manual grading
"""
import json
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from utils.rbac import (
    require_auth, require_role, verify_exam_access,
    get_user_courses, get_course_exams
)

exam_bp = Blueprint('exams', __name__, url_prefix='/api/exams')


def get_supabase():
    """Get Supabase client - must be initialized in main app"""
    from utils.supabase_client import get_supabase as _get
    return _get()


@exam_bp.route('/courses', methods=['GET'])
@require_auth
def get_user_courses_endpoint():
    """Get courses for logged-in user"""
    try:
        user = g.user
        supabase = get_supabase()
        
        courses = get_user_courses(supabase, user['id'])
        return jsonify({
            'success': True,
            'data': courses
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@exam_bp.route('/by-course/<course_id>', methods=['GET'])
@require_auth
def get_exams_by_course(course_id):
    """Get exams for a specific course"""
    try:
        user = g.user
        supabase = get_supabase()
        
        # Verify user has access to course
        from utils.rbac import verify_course_access
        if user['role'] == 'student':
            if not verify_course_access(supabase, user['id'], course_id):
                return jsonify({
                    'success': False,
                    'error': 'You do not have access to this course'
                }), 403
        
        exams = get_course_exams(supabase, course_id)
        
        # Filter based on user role
        if user['role'] == 'student':
            exams = [e for e in exams if e.get('status') == 'published']
        
        return jsonify({
            'success': True,
            'data': exams
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@exam_bp.route('/teacher/courses-with-exams', methods=['GET'])
@require_auth
@require_role('teacher')
def get_teacher_courses_with_exams():
    """Get all courses for teacher with exam counts and stats"""
    try:
        user = g.user
        supabase = get_supabase()
        
        # Get all courses for this teacher
        courses = get_user_courses(supabase, user['id'], role='teacher')
        
        # Enhance each course with exam stats
        result = []
        for course in courses:
            course_code = course.get('course_code')
            exams = get_course_exams(supabase, course_code)
            
            result.append({
                'course_code': course_code,
                'enrollment_role': course.get('enrollment_role'),
                'exam_count': len(exams),
                'published_count': len([e for e in exams if e.get('status') == 'published']),
                'draft_count': len([e for e in exams if e.get('status') == 'draft']),
            })
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@exam_bp.route('/admin/stats', methods=['GET'])
@require_auth
@require_role('admin')
def get_admin_stats():
    """Get system statistics for admin dashboard"""
    try:
        supabase = get_supabase()
        
        # Get user stats
        users_result = supabase.table('users').select('id, role').execute()
        users = users_result.data or []
        
        user_stats = {
            'total': len(users),
            'teachers': len([u for u in users if u['role'] == 'teacher']),
            'students': len([u for u in users if u['role'] == 'student']),
            'admins': len([u for u in users if u['role'] == 'admin']),
        }
        
        # Get course stats
        enrollments_result = supabase.table('course_enrollments').select(
            'course_code'
        ).eq('enrollment_status', 'active').execute()
        enrollments = enrollments_result.data or []
        
        unique_courses = len(set(e.get('course_code') for e in enrollments))
        
        course_stats = {
            'total_enrollments': len(enrollments),
            'unique_courses': unique_courses,
        }
        
        return jsonify({
            'success': True,
            'data': {
                'users': user_stats,
                'courses': course_stats,
            }
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@exam_bp.route('/admin/enrollments', methods=['GET'])
@require_auth
@require_role('admin')
def get_all_enrollments():
    """Get all course enrollments for admin (with pagination support)"""
    try:
        supabase = get_supabase()
        
        # Get page parameter (limit results)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        offset = (page - 1) * per_page
        
        # Get enrollments with user data
        enrollments_result = supabase.table('course_enrollments').select(
            'enrollment_id, user_id, course_code, enrollment_role, enrollment_status, enrolled_at'
        ).eq('enrollment_status', 'active').range(offset, offset + per_page - 1).execute()
        
        enrollments = enrollments_result.data or []
        
        # Get user info for enrollment users
        user_ids = list(set(e.get('user_id') for e in enrollments if e.get('user_id')))
        user_data = {}
        if user_ids:
            users_result = supabase.table('users').select(
                'id, email, role, first_name, last_name'
            ).execute()
            for user in users_result.data or []:
                user_data[user['id']] = user
        
        # Merge user data with enrollments
        enriched = []
        for enroll in enrollments:
            user = user_data.get(enroll.get('user_id'), {})
            enriched.append({
                'enrollment_id': enroll.get('enrollment_id'),
                'course_code': enroll.get('course_code'),
                'enrollment_role': enroll.get('enrollment_role'),
                'enrolled_at': enroll.get('enrolled_at'),
                'user_email': user.get('email', 'N/A'),
                'user_name': f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or 'Unknown',
            })
        
        return jsonify({
            'success': True,
            'data': enriched,
            'page': page,
            'per_page': per_page,
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



@exam_bp.route('/generate', methods=['POST'])
@require_auth
@require_role('teacher')
def generate_exam():
    """
    Generate exam questions from uploaded materials
    
    Request:
    {
        "course_id": "uuid",
        "exam_title": "string",
        "exam_description": "string",
        "materials": ["text1", "text2"],
        "num_questions": 10,
        "question_types": ["mcq", "essay"],
        "difficulty": "easy|medium|hard"
    }
    """
    try:
        user = g.user
        supabase = get_supabase()
        data = request.get_json() or {}
        
        # Validate required fields
        required_fields = ['course_id', 'exam_title', 'materials']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        # Verify course ownership
        course_result = supabase.table('courses').select(
            'course_id, teacher_id'
        ).eq('course_id', data['course_id']).execute()
        
        if not course_result.data or course_result.data[0]['teacher_id'] != user['id']:
            return jsonify({
                'success': False,
                'error': 'You do not have permission to generate exams for this course'
            }), 403
        
        # Generate questions using AI model
        from models.question_generator import generate_questions_from_text
        
        materials_text = '\n'.join(data['materials'])
        num_questions = data.get('num_questions', 10)
        question_types = data.get('question_types', ['mcq'])
        
        questions = generate_questions_from_text(
            materials_text,
            num_questions=num_questions,
            question_types=question_types
        )
        
        if not questions or len(questions) == 0:
            return jsonify({
                'success': False,
                'error': 'Failed to generate questions. Please try with different materials.'
            }), 400
        
        # Create exam record
        exam_id = str(uuid.uuid4())
        exam_data = {
            'exam_id': exam_id,
            'course_id': data['course_id'],
            'teacher_id': user['id'],
            'exam_title': data['exam_title'],
            'exam_description': data.get('exam_description', ''),
            'questions': json.dumps(questions),
            'status': 'draft',
            'total_marks': len(questions) * 10,  # Assume 10 marks per question
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        result = supabase.table('exams').insert(exam_data).execute()
        
        if not result.data:
            return jsonify({
                'success': False,
                'error': 'Failed to create exam'
            }), 500
        
        return jsonify({
            'success': True,
            'exam_id': exam_id,
            'questions': questions,
            'message': f'Generated {len(questions)} questions successfully'
        }), 201
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@exam_bp.route('/<exam_id>', methods=['GET'])
def get_exam_detail(exam_id):
    """Get exam details — accepts X-User headers or Bearer token"""
    try:
        supabase = get_supabase()

        # Resolve user from X-User headers (legacy) or Bearer token
        user_id = request.headers.get('X-User-ID', '').strip()
        user_role = (request.headers.get('X-User-Role') or '').strip().lower()

        if not user_id:
            # Try Bearer token via Supabase
            auth_header = (request.headers.get('Authorization') or '').strip()
            if auth_header.lower().startswith('bearer '):
                bearer = auth_header.split(' ', 1)[1].strip()
                if bearer:
                    try:
                        auth_resp = supabase.auth.get_user(bearer)
                        auth_user = getattr(auth_resp, 'user', None)
                        auth_email = str(getattr(auth_user, 'email', '') or '').strip().lower()
                        auth_uid = str(getattr(auth_user, 'id', '') or '').strip()
                        if auth_email:
                            from utils.supabase_client import get_supabase as _gs
                            sb = _gs()
                            profile_resp = sb.table('users').select('id,role,status').eq('email', auth_email).limit(1).execute()
                            if profile_resp.data:
                                profile = profile_resp.data[0]
                                user_id = str(profile.get('id') or auth_uid).strip()
                                user_role = str(profile.get('role') or '').strip().lower()
                    except Exception:
                        pass

        if not user_id or not user_role:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401

        # Verify access
        if not verify_exam_access(supabase, user_id, exam_id, user_role):
            return jsonify({'success': False, 'error': 'You do not have access to this exam'}), 403
        
        result = supabase.table('exams').select(
            '*'
        ).eq('exam_id', exam_id).execute()
        
        if not result.data:
            return jsonify({
                'success': False,
                'error': 'Exam not found'
            }), 404
        
        exam = result.data[0]
        
        # Parse questions if string
        if isinstance(exam.get('questions'), str):
            try:
                exam['questions'] = json.loads(exam['questions'])
            except:
                exam['questions'] = []
        
        return jsonify({
            'success': True,
            'data': exam
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@exam_bp.route('/<exam_id>/publish', methods=['POST'])
@require_auth
@require_role('teacher')
def publish_exam(exam_id):
    """Publish exam (make visible to students)"""
    try:
        user = g.user
        supabase = get_supabase()
        
        # Verify ownership
        exam_result = supabase.table('exams').select(
            'exam_id, teacher_id, status'
        ).eq('exam_id', exam_id).execute()
        
        if not exam_result.data or exam_result.data[0]['teacher_id'] != user['id']:
            return jsonify({
                'success': False,
                'error': 'You do not have permission to publish this exam'
            }), 403
        
        # Update status
        updated = supabase.table('exams').update({
            'status': 'published',
            'updated_at': datetime.utcnow().isoformat()
        }).eq('exam_id', exam_id).execute()
        
        return jsonify({
            'success': True,
            'message': 'Exam published successfully'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# STUDENT EXAM ATTEMPT ENDPOINTS
# ============================================

@exam_bp.route('/attempts/start', methods=['POST'])
@require_auth
@require_role('student')
def start_exam_attempt():
    """
    Start a new exam attempt
    
    Request:
    {
        "exam_id": "uuid"
    }
    """
    try:
        user = g.user
        supabase = get_supabase()
        data = request.get_json() or {}
        
        exam_id = data.get('exam_id')
        if not exam_id:
            return jsonify({
                'success': False,
                'error': 'exam_id required'
            }), 400
        
        # Verify exam access
        if not verify_exam_access(supabase, user['id'], exam_id, 'student'):
            return jsonify({
                'success': False,
                'error': 'You do not have access to this exam'
            }), 403
        
        # Check if already attempted
        existing = supabase.table('exam_attempts').select(
            'attempt_id'
        ).eq('exam_id', exam_id).eq('student_id', user['id']).execute()
        
        if existing.data and len(existing.data) > 0:
            # Return existing attempt
            return jsonify({
                'success': True,
                'attempt_id': existing.data[0]['attempt_id'],
                'message': 'Resuming previous attempt'
            }), 200
        
        # Create new attempt
        attempt_id = str(uuid.uuid4())
        attempt_data = {
            'attempt_id': attempt_id,
            'exam_id': exam_id,
            'student_id': user['id'],
            'status': 'in_progress',
            'start_time': datetime.utcnow().isoformat(),
            'submitted_answers': json.dumps({}),
            'percentage': 0,
            'created_at': datetime.utcnow().isoformat()
        }
        
        result = supabase.table('exam_attempts').insert(attempt_data).execute()
        
        if not result.data:
            return jsonify({
                'success': False,
                'error': 'Failed to create exam attempt'
            }), 500
        
        return jsonify({
            'success': True,
            'attempt_id': attempt_id,
            'message': 'Exam attempt started'
        }), 201
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@exam_bp.route('/attempts/<attempt_id>/submit', methods=['POST'])
@require_auth
@require_role('student')
def submit_exam_attempt(attempt_id):
    """
    Submit completed exam attempt
    
    Request:
    {
        "answers": {
            "q1": "answer_text",
            "q2": "B"
        }
    }
    """
    try:
        user = g.user
        supabase = get_supabase()
        data = request.get_json() or {}
        
        answers = data.get('answers', {})
        if not answers:
            return jsonify({
                'success': False,
                'error': 'No answers provided'
            }), 400
        
        # Get attempt
        attempt_result = supabase.table('exam_attempts').select(
            'attempt_id, exam_id, student_id'
        ).eq('attempt_id', attempt_id).execute()
        
        if not attempt_result.data or attempt_result.data[0]['student_id'] != user['id']:
            return jsonify({
                'success': False,
                'error': 'Attempt not found or access denied'
            }), 403
        
        attempt = attempt_result.data[0]
        
        # Update attempt
        updated = supabase.table('exam_attempts').update({
            'status': 'submitted',
            'end_time': datetime.utcnow().isoformat(),
            'submitted_answers': json.dumps(answers)
        }).eq('attempt_id', attempt_id).execute()
        
        # Trigger auto-grading (async)
        # In production, use Celery or similar
        
        return jsonify({
            'success': True,
            'attempt_id': attempt_id,
            'message': 'Exam submitted successfully'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@exam_bp.route('/attempts/<attempt_id>', methods=['GET'])
@require_auth
def get_attempt_detail(attempt_id):
    """Get exam attempt details"""
    try:
        user = g.user
        supabase = get_supabase()
        
        result = supabase.table('exam_attempts').select(
            '*'
        ).eq('attempt_id', attempt_id).execute()
        
        if not result.data:
            return jsonify({
                'success': False,
                'error': 'Attempt not found'
            }), 404
        
        attempt = result.data[0]
        
        # Verify access
        if attempt['student_id'] != user['id'] and user['role'] != 'teacher':
            return jsonify({
                'success': False,
                'error': 'Access denied'
            }), 403
        
        # Parse JSON fields
        if isinstance(attempt.get('submitted_answers'), str):
            try:
                attempt['submitted_answers'] = json.loads(attempt['submitted_answers'])
            except:
                attempt['submitted_answers'] = {}
        
        return jsonify({
            'success': True,
            'data': attempt
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@exam_bp.route('/attempts/<attempt_id>/marks', methods=['PUT'])
@require_auth
@require_role('teacher')
def update_attempt_marks(attempt_id):
    """
    Manually update marks for an attempt
    
    Request:
    {
        "manual_marks": 45,
        "comments": "Good effort"
    }
    """
    try:
        data = request.get_json() or {}
        
        if 'manual_marks' not in data:
            return jsonify({
                'success': False,
                'error': 'manual_marks required'
            }), 400
        
        update_data = {
            'manual_marks': float(data['manual_marks']),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        if 'comments' in data:
            update_data['teacher_comments'] = data['comments']
        
        updated = get_supabase().table('exam_attempts').update(
            update_data
        ).eq('attempt_id', attempt_id).execute()
        
        return jsonify({
            'success': True,
            'message': 'Marks updated successfully'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
