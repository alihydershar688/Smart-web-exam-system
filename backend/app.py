"""
AI-Based Smart Exam Web System - Backend API
Integrates Question Generation, Essay Grading, and Topic Extraction
"""
import sys
import os
# Ensure the backend directory is in Python path so 'models' package is found
# This is needed when running from a parent directory (e.g., Render deployment)
_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('smart_exam')

import builtins
# Windows terminals may use cp1252 and crash on emoji/unicode logs.
# Patch print once so logging never breaks request handling.
if not hasattr(builtins, "_smart_exam_original_print"):
    builtins._smart_exam_original_print = builtins.print
    def _smart_exam_safe_print(*args, **kwargs):
        try:
            builtins._smart_exam_original_print(*args, **kwargs)
        except UnicodeEncodeError:
            safe_args = [str(a).encode("ascii", "replace").decode("ascii") for a in args]
            builtins._smart_exam_original_print(*safe_args, **kwargs)
    builtins.print = _smart_exam_safe_print
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import time
import uuid
import re
from dotenv import load_dotenv
load_dotenv()  # Must run before model imports so OLLAMA_HOST is available
from werkzeug.utils import secure_filename
import traceback
# Import utility functions
from utils.pdf_processor import extract_text_from_file
from utils.supabase_client import get_supabase
from utils.admin_control import (
    load_admin_control,
    save_admin_control,
    is_authorized_admin,
    is_active_admin,
    public_summary,
    record_transfer,
)
from utils.session_lock import (
    load_session_locks,
    save_session_locks,
    acquire_session_lock,
    renew_session_lock,
    release_session_lock,
)
from utils.exam_operations import exam_bp
app = Flask(__name__)
# Enable CORS for all origins
CORS(app,
     origins="*",
     allow_headers=["*"],
     expose_headers=["*"],
     supports_credentials=False,
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
# Register exam operations blueprint for RBAC
app.register_blueprint(exam_bp)

# Extract auth context from headers for RBAC
@app.before_request
def extract_auth_context():
    from utils.rbac import extract_user_from_auth_header
    from flask import g
    g.user = extract_user_from_auth_header()
def _env_float(name, default):
    raw = os.getenv(name, str(default))
    try:
        return float(raw)
    except Exception:
        return float(default)
AI_CONFIDENCE_THRESHOLD = max(0.0, min(1.0, _env_float("AI_CONFIDENCE_THRESHOLD", 0.75)))

_QUESTION_GENERATOR_MODULE = None
_ESSAY_GRADER_MODULE = None
_TOPIC_EXTRACTOR_MODULE = None


def _load_question_generator_module():
    global _QUESTION_GENERATOR_MODULE
    if _QUESTION_GENERATOR_MODULE is None:
        try:
            from models import question_generator as module
        except ImportError:
            import importlib.util, os
            spec = importlib.util.spec_from_file_location(
                'question_generator',
                os.path.join(os.path.dirname(__file__), 'models', 'question_generator.py')
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        _QUESTION_GENERATOR_MODULE = module
    return _QUESTION_GENERATOR_MODULE


def _load_essay_grader_module():
    global _ESSAY_GRADER_MODULE
    if _ESSAY_GRADER_MODULE is None:
        try:
            from models import essay_grader as module
        except ImportError:
            import importlib.util, os
            spec = importlib.util.spec_from_file_location(
                'essay_grader',
                os.path.join(os.path.dirname(__file__), 'models', 'essay_grader.py')
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        _ESSAY_GRADER_MODULE = module
    return _ESSAY_GRADER_MODULE


def _load_topic_extractor_module():
    global _TOPIC_EXTRACTOR_MODULE
    if _TOPIC_EXTRACTOR_MODULE is None:
        try:
            from models import topic_extractor as module
        except ImportError:
            import importlib.util, os
            spec = importlib.util.spec_from_file_location(
                'topic_extractor',
                os.path.join(os.path.dirname(__file__), 'models', 'topic_extractor.py')
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        _TOPIC_EXTRACTOR_MODULE = module
    return _TOPIC_EXTRACTOR_MODULE


def generate_questions_from_text(*args, **kwargs):
    return _load_question_generator_module().generate_questions_from_text(*args, **kwargs)


def get_generation_model_status(force_load=False):
    if force_load:
        return _load_question_generator_module().get_generation_model_status()

    if _QUESTION_GENERATOR_MODULE is not None:
        return _QUESTION_GENERATOR_MODULE.get_generation_model_status()

    return {
        'loaded': False,
        'lazy_import': True,
        'use_qwen_lora': str(os.getenv('USE_QWEN_LORA', 'false')).strip().lower() == 'true',
        'qwen_base_model': os.getenv('QWEN_BASE_MODEL', ''),
        'qwen_pipeline_loaded': False,
        'qwen_load_attempted': False,
        'qwen_lora_adapter_present': False,
        'ollama_available': False,
        'ollama_model': os.getenv('OLLAMA_MODEL', ''),
        'device': 'uninitialized',
    }


def grade_essay(*args, **kwargs):
    return _load_essay_grader_module().grade_essay(*args, **kwargs)


def preload_sbert():
    return _load_essay_grader_module().preload_sbert()


def extract_topics_from_text(*args, **kwargs):
    return _load_topic_extractor_module().extract_topics_from_text(*args, **kwargs)


def classify_subject(*args, **kwargs):
    return _load_topic_extractor_module().classify_subject(*args, **kwargs)


def classify_code_concept(*args, **kwargs):
    return _load_topic_extractor_module().classify_code_concept(*args, **kwargs)


def preload_all_models():
    return _load_topic_extractor_module().preload_all_models()


def _bearer_token():
    header = (request.headers.get('Authorization') or '').strip()
    if not header.lower().startswith('bearer '):
        return None
    token = header.split(' ', 1)[1].strip()
    return token or None


def _require_authenticated_user():
    token = _bearer_token()
    if not token:
        return None, (jsonify({'success': False, 'error': 'Authentication required'}), 401)

    try:
        supabase = get_supabase()
        auth_response = supabase.auth.get_user(token)
        auth_user = getattr(auth_response, 'user', None)
        auth_email = (getattr(auth_user, 'email', '') or '').strip().lower()
        auth_user_id = str(getattr(auth_user, 'id', '') or '').strip()
        if not auth_email:
            raise ValueError('Authenticated user email is missing')

        profile = _load_user_profile_for_auth(supabase, auth_email, auth_user_id)
        return {
            'auth_id': auth_user_id,
            'email': auth_email,
            'role': str(profile.get('role') or '').strip().lower(),
            'status': str(profile.get('status') or '').strip().lower(),
            'admin_id': (profile.get('admin_id') or '').strip(),
            'profile': profile,
        }, None
    except Exception as exc:
        logger.warning("[admin-auth] Failed to authenticate request: %s", exc)
        return None, (jsonify({'success': False, 'error': 'Invalid or expired session'}), 401)


def _load_user_profile_for_auth(supabase, auth_email, auth_user_id):
    if not supabase:
        return {}
    candidate_columns = ['id', 'user_id', 'auth_id', 'uuid']
    for column in candidate_columns:
        try:
            resp = db_exec(
                lambda column=column: supabase.table('users')
                .select('*')
                .eq(column, auth_user_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if _is_missing_column_error(exc):
                continue
            raise
        if resp.data:
            return resp.data[0]
    try:
        profile_resp = db_exec(
            lambda: supabase.table('users').select('*').eq('email', auth_email).limit(1).execute()
        )
        return profile_resp.data[0] if profile_resp.data else {}
    except Exception:
        return {}


def _require_active_admin(payload=None):
    user_ctx, auth_error = _require_authenticated_user()
    if auth_error:
        return None, None, auth_error

    identity = {
        'email': user_ctx.get('email'),
        'admin_id': user_ctx.get('admin_id'),
        'auth_id': user_ctx.get('auth_id'),
    }
    state = load_admin_control()
    # Any active admin in the database has full access
    if user_ctx.get('role') != 'admin' or user_ctx.get('status') != 'active':
        return None, identity, (jsonify({'success': False, 'error': 'Forbidden: active admin account required'}), 403)
    return state, identity, None


def _require_authorized_admin(payload=None):
    user_ctx, auth_error = _require_authenticated_user()
    if auth_error:
        return None, None, auth_error

    identity = {
        'email': user_ctx.get('email'),
        'admin_id': user_ctx.get('admin_id'),
        'auth_id': user_ctx.get('auth_id'),
    }
    state = load_admin_control()
    # Any active admin in the database has full access — no JSON file check needed
    if user_ctx.get('role') != 'admin' or user_ctx.get('status') != 'active':
        return None, identity, (jsonify({'success': False, 'error': 'Forbidden: active admin account required'}), 403)
    return state, identity, None


def _require_session_lock_payload(payload=None):
    payload = payload or {}
    user_ctx, auth_error = _require_authenticated_user()
    if auth_error:
        return None, auth_error

    email = str(payload.get('email') or '').strip().lower()
    role = str(payload.get('role') or '').strip().lower()
    device_id = str(payload.get('device_id') or '').strip()

    if not email or not role or not device_id:
        return None, (jsonify({'success': False, 'error': 'email, role, and device_id are required'}), 400)
    if email != user_ctx.get('email') or role != user_ctx.get('role'):
        return None, (jsonify({'success': False, 'error': 'Session lock identity does not match authenticated user'}), 403)
    if user_ctx.get('status') != 'active':
        return None, (jsonify({'success': False, 'error': 'Active account required'}), 403)

    return {
        'email': email,
        'role': role,
        'device_id': device_id,
    }, None


def _optional_authenticated_user():
    if not _bearer_token():
        return None, None
    return _require_authenticated_user()


def _is_valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


def _user_ctx_profile_id(user_ctx):
    profile = (user_ctx or {}).get('profile') or {}
    candidates = [
        profile.get('id'),
        profile.get('user_id'),
        profile.get('teacher_id'),
        profile.get('student_id'),
        profile.get('admin_id'),
        (user_ctx or {}).get('auth_id'),
    ]
    for candidate in candidates:
        if _is_valid_uuid(candidate):
            return str(candidate)
    fallback = next((str(candidate).strip() for candidate in candidates if str(candidate or '').strip()), '')
    return fallback or None


def _require_authenticated_roles(*allowed_roles, active_only=True):
    user_ctx, auth_error = _require_authenticated_user()
    if auth_error:
        return None, auth_error

    role = str(user_ctx.get('role') or '').strip().lower()
    if allowed_roles and role not in {str(value).strip().lower() for value in allowed_roles}:
        allowed_label = ', '.join(sorted({str(value).strip().lower() for value in allowed_roles}))
        return None, (jsonify({'success': False, 'error': f'Forbidden: {allowed_label} access required'}), 403)
    if active_only and str(user_ctx.get('status') or '').strip().lower() != 'active':
        return None, (jsonify({'success': False, 'error': 'Active account required'}), 403)
    return user_ctx, None


def _load_exam_row(supabase, exam_id, fields='*'):
    response = db_exec(lambda: supabase.table('exams').select(fields).eq('exam_id', exam_id).limit(1).execute())
    if response.data:
        return dict(response.data[0] or {})
    response = db_exec(lambda: supabase.table('exams').select(fields).eq('id', exam_id).limit(1).execute())
    if response.data:
        return dict(response.data[0] or {})
    return None


def _load_attempt_row(supabase, attempt_id, fields='*'):
    response = db_exec(lambda: supabase.table('exam_attempts').select(fields).eq('attempt_id', attempt_id).limit(1).execute())
    if response.data:
        return dict(response.data[0] or {})
    return None


def _require_teacher_exam_owner(supabase, exam_id, user_ctx):
    exam_row = _load_exam_row(supabase, exam_id, 'exam_id,id,teacher_id,course_id,status,is_visible_to_students')
    if not exam_row:
        return None, (jsonify({'success': False, 'error': 'Exam not found'}), 404)
    teacher_user_id = _user_ctx_profile_id(user_ctx)
    owner_id = str(exam_row.get('teacher_id') or '').strip()
    if not teacher_user_id or (owner_id and owner_id != str(teacher_user_id)):
        return None, (jsonify({'success': False, 'error': 'Forbidden: exam does not belong to this teacher'}), 403)
    return exam_row, None


def _question_payload_for_candidate(question_row):
    question = dict(question_row or {})
    for field in ('correct_answer', 'model_answer', 'explanation', 'ai_feedback'):
        question.pop(field, None)
    return question


def _can_student_view_exam(exam_row):
    status = str((exam_row or {}).get('status') or '').strip().lower()
    visible = (exam_row or {}).get('is_visible_to_students')
    return status == 'published' or visible is True


def _load_course_row(supabase, course_id, fields='*'):
    if not course_id:
        return None
    response = db_exec(lambda: supabase.table('courses').select(fields).eq('id', course_id).limit(1).execute())
    if response.data:
        return dict(response.data[0] or {})
    return None


def _is_active_enrollment(enrollment_row):
    row = dict(enrollment_row or {})

    # If approved column exists and is explicitly False, reject
    approved = row.get('approved')
    if approved is False:
        return False

    status = str(row.get('status') or '').strip().lower()
    if status in {'pending', 'rejected', 'inactive', 'suspended', 'revoked'}:
        return False

    # approval_status column may not exist — only reject if explicitly bad
    approval_status = str(row.get('approval_status') or '').strip().lower()
    if approval_status and approval_status in {'pending', 'rejected', 'inactive'}:
        return False

    # Default: treat as active if status is 'active' or empty (newly inserted rows)
    return status in {'active', ''} or not status


def _load_student_enrollments(supabase, student_id):
    if not student_id:
        return []

    # Primary: use the enrollments table (student_id + course_id)
    try:
        response = db_exec(lambda: supabase.table('enrollments').select('*').eq('student_id', student_id).execute())
        rows = response.data or []
        active = [dict(row or {}) for row in rows if _is_active_enrollment(row)]
        if active:
            return active
    except Exception:
        pass

    # Fallback: legacy course_enrollments table (user_id + course_code)
    try:
        response = db_exec(lambda: supabase.table('course_enrollments')
            .select('course_code')
            .eq('user_id', student_id)
            .eq('enrollment_role', 'student')
            .eq('enrollment_status', 'active')
            .execute())
        if response.data:
            course_codes = [row['course_code'] for row in response.data if row.get('course_code')]
            if course_codes:
                courses_response = db_exec(lambda: supabase.table('courses')
                    .select('id, course_code')
                    .in_('course_code', course_codes)
                    .execute())
                return [
                    {'course_id': c.get('id'), 'course_code': c.get('course_code'), 'status': 'active'}
                    for c in (courses_response.data or [])
                ]
    except Exception:
        pass

    return []


def _load_student_course_ids(supabase, student_id):
    course_ids = set()
    for row in _load_student_enrollments(supabase, student_id):
        course_id = str(row.get('course_id') or '').strip()
        if course_id:
            course_ids.add(course_id)
    return course_ids


def _normalize_scope_value(value):
    return str(value or '').strip().lower()


def _student_matches_exam_scope(user_ctx, exam_row):
    profile = (user_ctx or {}).get('profile') or {}
    for field in ('semester', 'section', 'batch'):
        exam_value = _normalize_scope_value((exam_row or {}).get(field))
        if not exam_value:
            continue
        profile_value = _normalize_scope_value(profile.get(field))
        if not profile_value or profile_value != exam_value:
            return False
    return True


def _student_can_access_exam(supabase, user_ctx, exam_row):
    if not _can_student_view_exam(exam_row):
        return False

    student_id = _user_ctx_profile_id(user_ctx)
    if not student_id:
        return False

    course_id = str((exam_row or {}).get('course_id') or '').strip()
    if not course_id:
        return False

    if course_id not in _load_student_course_ids(supabase, student_id):
        return False

    return _student_matches_exam_scope(user_ctx, exam_row)


def _require_teacher_course_owner(supabase, course_id, user_ctx):
    if not _is_valid_uuid(course_id):
        return None, (jsonify({'error': 'A valid course is required'}), 400)

    course_row = _load_course_row(supabase, course_id, 'id,teacher_id,course_code,course_name')
    if not course_row:
        return None, (jsonify({'error': 'Selected course was not found'}), 404)

    teacher_user_id = str(_user_ctx_profile_id(user_ctx) or '').strip()
    owner_id = str(course_row.get('teacher_id') or '').strip()
    if not teacher_user_id or not owner_id or owner_id != teacher_user_id:
        return None, (jsonify({'error': 'Forbidden: selected course does not belong to this teacher'}), 403)

    return course_row, None


def _load_user_row_by_identifier(supabase, user_identifier, fields='*'):
    if not user_identifier:
        return None
    identifier = str(user_identifier).strip()

    # If it looks like an email, try email column first
    if '@' in identifier:
        try:
            response = db_exec(
                lambda: supabase.table('users').select(fields).eq('email', identifier).limit(1).execute()
            )
            if response.data:
                return dict(response.data[0] or {})
        except Exception:
            pass
        return None

    # Otherwise try UUID/ID columns
    for field_name in ('id', 'user_id', 'student_id', 'teacher_id', 'admin_id'):
        try:
            response = db_exec(
                lambda field_name=field_name: supabase.table('users').select(fields).eq(field_name, identifier).limit(1).execute()
            )
        except Exception as exc:
            if _is_missing_column_error(exc):
                continue
            raise
        if response.data:
            return dict(response.data[0] or {})
    return None


def _serialize_course_summary(course_row):
    row = dict(course_row or {})
    course_id = row.get('id') or row.get('course_id')
    return {
        'id': course_id,
        'course_id': course_id,
        'course_code': row.get('course_code'),
        'course_name': row.get('course_name') or row.get('name') or 'Course',
        'semester': row.get('semester'),
        'academic_year': row.get('academic_year'),
        'teacher_id': row.get('teacher_id')
    }


def _is_missing_column_error(err):
    message = str(err or '').strip().lower()
    if not message:
        return False
    return (
        'column' in message
        and (
            'does not exist' in message
            or 'schema cache' in message
            or 'could not find the' in message
        )
    )


def _activate_enrollment_record(supabase, enrollment_id):
    update_candidates = [
        {'status': 'active', 'approved': True, 'approval_status': 'approved'},
        {'status': 'active', 'approved': True},
        {'status': 'active'},
    ]
    last_error = None
    for payload in update_candidates:
        try:
            db_exec(
                lambda payload=payload, enrollment_id=enrollment_id: supabase.table('enrollments')
                .update(payload)
                .eq('enrollment_id', enrollment_id)
                .execute()
            )
            return
        except Exception as exc:
            last_error = exc
            if not _is_missing_column_error(exc):
                raise
    if last_error:
        raise last_error


def _create_active_enrollment_record(supabase, student_id, course_id):
    enrolled_at = time.strftime('%Y-%m-%d %H:%M:%S')
    insert_candidates = [
        {
            'student_id': student_id,
            'course_id': course_id,
            'status': 'active',
            'approved': True,
            'approval_status': 'approved',
            'enrolled_at': enrolled_at,
        },
        {
            'student_id': student_id,
            'course_id': course_id,
            'status': 'active',
            'approved': True,
            'enrolled_at': enrolled_at,
        },
        {
            'student_id': student_id,
            'course_id': course_id,
            'status': 'active',
            'enrolled_at': enrolled_at,
        },
    ]
    last_error = None
    for payload in insert_candidates:
        try:
            db_exec(lambda payload=payload: supabase.table('enrollments').insert(payload).execute())
            return
        except Exception as exc:
            last_error = exc
            if not _is_missing_column_error(exc):
                raise
    if last_error:
        raise last_error


@app.route('/', methods=['GET'])
def root():
    """Simple root route to avoid confusion when opening backend URL directly."""
    return jsonify({
        'message': 'Smart Exam backend is running',
        'api_base': '/api',
        'health': '/api/health'
    }), 200
# Add response headers for CORS
@app.after_request
def after_request(response):
    # flask_cors already injects CORS headers — nothing extra needed here.
    return response
# Handle OPTIONS requests (CORS preflight)
@app.route('/api/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    # Let flask_cors inject the CORS headers to avoid duplicates.
    return ('', 204)
# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'pptx', 'ppt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 # 50MB max
# Create upload folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
def _is_transient_db_error(err):
    msg = str(err).lower()
    transient_markers = (
        'winerror 10035',
        'timed out',
        'timeout',
        'connection aborted',
        'connection reset',
        'temporarily unavailable',
        'network',
        'errno 11',
        'json could not be generated',
        'internal server error',
        'cloudflare',
        '502 bad gateway',
        '503 service unavailable',
        '504 gateway timeout'
    )
    return any(m in msg for m in transient_markers)
def db_exec(op, retries=3, base_delay=0.35):
    """
    Execute a Supabase operation with lightweight retry for transient socket/network errors.
    """
    last_err = None
    for attempt in range(retries):
        try:
            return op()
        except Exception as e:
            last_err = e
            if attempt < retries - 1 and _is_transient_db_error(e):
                time.sleep(base_delay * (attempt + 1))
                continue
            raise
    raise last_err
def _sanitize_text(value):
    if value is None:
        return None
    text = str(value)
    # Postgres text/json cannot contain NUL bytes.
    text = text.replace('\x00', '')
    # Keep printable + common whitespace.
    text = re.sub(r'[\u0001-\u0008\u000B\u000C\u000E-\u001F]', ' ', text)
    return text.strip()
def _sanitize_jsonish(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return {_sanitize_text(k): _sanitize_jsonish(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_jsonish(v) for v in value]
    if isinstance(value, (int, float, bool)):
        return value
    return _sanitize_text(value)
def _sanitize_question_payload(questions):
    cleaned = []
    for q in (questions or []):
        if not isinstance(q, dict):
            continue
        cq = dict(q)
        cq['question_text'] = _sanitize_text(q.get('question_text') or q.get('question'))
        cq['explanation'] = _sanitize_text(q.get('explanation'))
        cq['model_answer'] = _sanitize_text(q.get('model_answer'))
        cq['topic'] = _sanitize_text(q.get('topic'))
        # Hard rule: only MCQ and True/False questions may carry options / correct_answer
        qt = to_db_question_type(q.get('question_type') or q.get('type') or '')
        if qt in ('mcq', 'true_false'):
            cq['options'] = _sanitize_jsonish(q.get('options'))
            cq['correct_answer'] = _sanitize_text(q.get('correct_answer'))
        else:
            cq['options'] = None
            cq['correct_answer'] = None
        cleaned.append(cq)
    return cleaned
def _safe_int(value, default=1):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except Exception:
        return default
def _extract_grading_confidence(grading_result):
    """
    Normalize confidence score to [0,1].
    Supports multiple possible key names from different grader outputs.
    """
    if not isinstance(grading_result, dict):
        return 0.0
    candidates = [
        grading_result.get('confidence'),
        grading_result.get('similarity'),
        grading_result.get('similarity_score'),
        grading_result.get('similarity_with_model'),
    ]
    for value in candidates:
        if value is None:
            continue
        try:
            c = float(value)
            # If confidence came as percentage, normalize.
            if c > 1.0:
                c = c / 100.0
            return max(0.0, min(1.0, c))
        except Exception:
            continue
    # Fallback: derive from achieved/max score.
    try:
        score = float(grading_result.get('score', 0))
        max_score = float(grading_result.get('max_score') or grading_result.get('max_marks') or 0)
        if max_score > 0:
            return max(0.0, min(1.0, score / max_score))
    except Exception:
        pass
    return 0.0
def _normalize_grading_result(grading_result, max_marks):
    """
    Convert grader output to a stable shape expected by API + DB fields.
    """
    if not isinstance(grading_result, dict):
        grading_result = {}
    try:
        raw_score = float(grading_result.get('score', 0))
    except Exception:
        raw_score = 0.0
    try:
        raw_max = float(grading_result.get('max_score', 10) or 10)
    except Exception:
        raw_max = 10.0
    max_marks = float(max_marks or raw_max or 10)
    if raw_max <= 0:
        raw_max = 10.0
    scaled_score = max(0.0, min(max_marks, (raw_score / raw_max) * max_marks))
    confidence = _extract_grading_confidence(grading_result)
    feedback = _sanitize_jsonish(grading_result)
    feedback['normalized_score'] = round(scaled_score, 2)
    feedback['normalized_max_marks'] = max_marks
    feedback['confidence'] = round(confidence, 4)
    feedback['threshold'] = AI_CONFIDENCE_THRESHOLD
    status = 'auto_graded' if confidence >= AI_CONFIDENCE_THRESHOLD else 'pending'
    return {
        'score': round(scaled_score, 2),
        'max_score': max_marks,
        'confidence': round(confidence, 4),
        'review_status': status,
        'feedback': feedback
    }
def _grade_essay_flex(question_text, reference_answer, student_answer, max_marks):
    """
    Backward/forward-compatible call for essay grader signature variants.
    """
    # New-style signature support
    try:
        return grade_essay(
            question_text=question_text,
            reference_answer=reference_answer,
            student_answer=student_answer,
            max_marks=max_marks
        )
    except TypeError:
        # Fallback for legacy signature:
        # grade_essay(essay_text, rubric=None, expected_keywords=None)
        keywords = []
        try:
            tokens = re.findall(r"[A-Za-z]{4,}", reference_answer or "")
            seen = set()
            for t in tokens:
                tl = t.lower()
                if tl not in seen:
                    seen.add(tl)
                    keywords.append(tl)
                if len(keywords) >= 12:
                    break
        except Exception:
            keywords = []
        return grade_essay(
            essay_text=student_answer or "",
            rubric=question_text or "",
            expected_keywords=keywords
        )
def _update_answer_with_fallback(supabase, answer_id, payload):
    """
    Update student_answers with graceful fallback if some columns do not exist.
    """
    update_payload = dict(payload or {})
    if 'max_marks' in update_payload:
        try:
            update_payload['max_marks'] = int(round(float(update_payload.get('max_marks') or 0)))
        except Exception:
            update_payload['max_marks'] = 0
    while True:
        resp = db_exec(lambda: supabase.table('student_answers').update(update_payload).eq('answer_id', answer_id).execute())
        err = getattr(resp, 'error', None)
        if not err:
            return resp
        msg = str(getattr(err, 'message', err))
        m = re.search(r"column\s+\"([^\"]+)\"\s+of relation", msg, re.IGNORECASE)
        if not m:
            raise Exception(msg)
        missing_col = m.group(1)
        if missing_col in update_payload:
            update_payload.pop(missing_col, None)
            if not update_payload:
                raise Exception(msg)
            continue
        raise Exception(msg)
def _recalculate_attempt_totals(supabase, attempt_id):
    """
    Recompute attempt totals and status from student_answers rows.
    """
    if not attempt_id:
        return None
    ans_resp = db_exec(lambda: supabase.table('student_answers').select(
        'marks_obtained,max_marks,review_status'
    ).eq('attempt_id', attempt_id).execute())
    answers = ans_resp.data if ans_resp.data else []
    total_score = 0.0
    total_max = 0.0
    pending_count = 0
    for a in answers:
        try:
            total_score += float(a.get('marks_obtained') or 0)
        except Exception:
            pass
        try:
            total_max += float(a.get('max_marks') or 0)
        except Exception:
            pass
        if str(a.get('review_status') or '').strip().lower() == 'pending':
            pending_count += 1
    percentage = (total_score / total_max * 100) if total_max > 0 else 0
    attempt_status = 'pending_grading' if pending_count > 0 else 'graded'
    update_payload = {
        'score': round(total_score, 2),
        'max_score': int(round(total_max)),
        'percentage': round(percentage, 2),
        'status': attempt_status,
        'is_graded': bool(attempt_status == 'graded'),
    }
    if attempt_status == 'graded':
        update_payload['graded_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    db_exec(lambda: supabase.table('exam_attempts').update(update_payload).eq('attempt_id', attempt_id).execute())
    return {
        'total_marks': round(total_score, 2),
        'total_max': round(total_max, 2),
        'percentage': round(percentage, 2),
        'pending_count': pending_count,
        'status': attempt_status
    }


def _norm_answer_token(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def _is_objective_correct(student_answer, correct_answer, options):
    """
    Compare objective answer robustly by key and option text.
    """
    student = _norm_answer_token(student_answer)
    correct = _norm_answer_token(correct_answer)
    if not student or not correct:
        return False
    if student == correct:
        return True

    if isinstance(options, dict):
        try:
            student_text = _norm_answer_token(options.get(str(student_answer).strip()))
            correct_text = _norm_answer_token(options.get(str(correct_answer).strip()))
            if student_text and correct_text and student_text == correct_text:
                return True
            # If UI stored full text instead of key.
            if correct_text and student == correct_text:
                return True
        except Exception:
            return False
    return False
def normalize_question_type(value):
    raw = (value or 'mcq').strip().lower().replace('-', '_').replace(' ', '_')
    mapping = {
        'mcq': 'MCQ',
        'multiple_choice': 'MCQ',
        'multiplechoice': 'MCQ',
        'true_false': 'MCQ',
        'truefalse': 'MCQ',
        'short_answer': 'Short Answer',
        'shortanswer': 'Short Answer',
        'long_answer': 'Long Answer',
        'longanswer': 'Long Answer',
        'essay': 'Long Answer',
        'descriptive': 'Long Answer'
    }
    return mapping.get(raw, 'MCQ')
def to_db_question_type(value):
    """Canonical DB-safe question type values."""
    raw = str(value or '').strip().lower()
    raw = raw.replace('-', '_').replace(' ', '_')
    mapping = {
        'mcq': 'mcq',
        'multiple_choice': 'mcq',
        'multiplechoice': 'mcq',
        'true_false': 'true_false',
        'truefalse': 'true_false',
        'tf': 'true_false',
        'short_answer': 'short_answer',
        'shortanswer': 'short_answer',
        'long_answer': 'long_answer',
        'longanswer': 'long_answer',
        'essay': 'long_answer',
        'code': 'code',
        'coding': 'code'
    }
    return mapping.get(raw, 'mcq')
def build_question_type_candidates(raw_value):
    base = to_db_question_type(raw_value)
    # DB is normalized to snake_case lowercase values.
    # Keep candidates strict to prevent publishing failures from legacy UI labels.
    return [base]
def is_objective_type(question_type):
    t = (question_type or '').strip().lower().replace(' ', '_').replace('-', '_')
    return t in ('mcq', 'true_false')
_FALLBACK_JUNK_PHRASES = (
    'about me', 'my name', 'teaching platform', 'youtube', 'project.eu',
    'start up', 'startup', 'hobby', 'hobbies', 'visited', 'maqbool',
    'personal home', 'copyright', 'all rights reserved',
    'worked with multinational', 'tourism', 'countries visited',
    'mid semester', 'final exam', 'assignment', 'quiz marks',
    'raise your hand', 'who has', 'course outline', 'learning outcomes',
    'prepared by', 'adapted from', 'modified from',
)
def _split_sentences_for_fallback(text):
    parts = re.split(r'[.!?\n]+', text or '')
    sentences = []
    _seen_sents = set()
    for p in parts:
        s = p.strip()
        if len(s) < 25:
            continue
        sl = s.lower()
        # Skip bio/junk/meta sentences so they never become fallback question stems
        if any(phrase in sl for phrase in _FALLBACK_JUNK_PHRASES):
            continue
        if re.search(r'https?://|www\.|project\.eu|youtube\.com', sl):
            continue
        if re.search(r'\d+\s*%', sl): # exam-schedule lines like "25%"
            continue
        # Skip numbered/bulleted slide headings like "10▪Manual File Storage"
        if re.match(r'^\d+[\s\u25aa\u25cf\u2022\u25ab\u2023\u00bb\*\-\.]', s):
            continue
        # Skip short title-case headings (slide section labels)
        words = s.split()
        if len(words) <= 6 and s == s.title():
            continue
        # Skip lines containing bullet/heading chars
        if any(c in s for c in '\u25aa\u25cf\u2022\u25ab\u2023\u00bb\u25a0\u25c6\u25e6\u25ba\u27a2\u27a4\u279c\u2794\u27a1\u25b9\u276f\u2756\u2666\u25c7\u2500\u254c\u00b0\u25b6\u2192\u2218\u2611\u2610\u25b8\u203a\u2713'):
            continue
        # Skip short colon-prefixed labels like "Working Project: -project" / "File: xyz"
        if re.match(r'^[\w\s]+:\s*\S', s) and len(s) < 60:
            continue
        # Skip fragments: less than 8 words, lowercase start, contain and/or
        if len(words) < 8:
            continue
        if s[0].islower():
            continue
        # Skip if contains 'and/or' (slide copypaste fragment)
        if 'and/or' in s:
            continue
        # Skip if last word is a dangling preposition/article (truncated fragment)
        if words[-1].lower().rstrip('.,;:?!') in _MCQ_DANGLE_WORDS:
            continue
        # Dedup: skip if we've already seen this sentence (same text repeated in different sections)
        s_lower = s.lower().strip()
        if s_lower in _seen_sents:
            continue
        _seen_sents.add(s_lower)
        sentences.append(s)
    if not sentences:
        sentences = ['Explain the key concept from the provided material.']
    return sentences
def _to_mcq_options(question_text, idx=0):
    """Build four real MCQ options — domain-specific, never garbage placeholders."""
    import random as _rng
    _rng.seed(hash(question_text or '') + idx)
    stem = (question_text or 'the topic').strip()
    if len(stem) > 120:
        stem = stem[:120].rsplit(' ', 1)[0]
    _POOL = [
        'Storing all records in a single flat file without any organized schema or access control',
        'Allowing every user to directly modify raw data without any validation or management layer',
        'Using no indexing strategy and performing sequential scans for every data retrieval request',
        'Keeping all data in memory without any persistent storage mechanism or backup procedure',
        'Requiring manual recalculation of all derived values whenever the underlying data changes',
        'Eliminating all constraints to maximize data entry speed regardless of accuracy or consistency',
        'Granting unrestricted write access to all tables without any authentication or user roles',
        'Relying on application programs to enforce all data consistency rules manually without DBMS support',
        'Defining no relationships between entities and treating all data as completely independent rows',
        'Duplicating all records across separate files with no mechanism to ensure data consistency',
        'Ignoring data types entirely and storing everything as unstructured plain text without validation',
        'Hardcoding all data validation rules inside each individual application program separately',
    ]
    picked = _rng.sample(_POOL, 3)
    return {
        'A': stem,
        'B': picked[0],
        'C': picked[1],
        'D': picked[2]
    }
# ── Topic validation & subject topic banks (for Short/Long stems) ────
def _is_valid_topic(topic):
    """Return True only if *topic* is clean enough for a question stem."""
    if not topic or len(topic.strip()) < 4:
        return False
    t = topic.strip()
    if re.search(r'[><=(){}\[\]$@#%^&;\\|/]', t):
        return False
    # CamelCase / run-together PDF artifacts (e.g. "RESEARCHSchID", "NameResID")
    if re.search(r'[a-z][A-Z]', t):
        return False
    # ALL-CAPS fragments longer than one word
    if len(t.split()) >= 2 and t == t.upper():
        return False
    last_word = t.split()[-1].lower().rstrip('.,;:')
    _DANGLE = {'a','an','the','in','on','at','by','to','of','for','with','from',
               'and','or','but','is','are','was','were','has','have','had','new',
               'into','its','their','those','these','not','no','any','all','each',
               'such','some','than','about','that','which','between'}
    if last_word in _DANGLE:
        return False
    first_word = t.split()[0].lower()
    _BAD_STARTS = {'it','this','that','they','he','she','we','you','there','here',
                   'no','any','when','while','where','if','although','because',
                   'once','so','yet','nor','but','and','or','however','furthermore'}
    if first_word in _BAD_STARTS:
        return False
    if t.count('"') % 2 != 0 or t.count("'") > 2 or ')' in t or '(' in t:
        return False
    digit_ratio = sum(1 for c in t if c.isdigit()) / max(1, len(t))
    if digit_ratio > 0.15:
        return False
    if len(t.split()) > 7:
        return False
    return True
# Map pool-key subjects to question_generator subject keys for bank lookup
_POOL_TO_BANK_SUBJECT = {
    'database': 'database_fundamentals',
    'python': 'python_programming',
    'oop': 'object_oriented_programming',
    'web': 'web_development',
    'se': 'software_engineering',
    'generic': 'general',
}
_APP_SUBJECT_TOPIC_BANKS = {
    'se': [
        'Requirements Engineering', 'Software Testing', 'Agile Development',
        'Waterfall Model', 'Risk Management', 'Software Maintenance',
        'Configuration Management', 'Code Refactoring', 'UML Diagrams',
        'Software Metrics', 'Version Control', 'Design Patterns',
        'Integration Testing', 'Continuous Integration', 'Use Case Modeling',
    ],
    'database': [
        'Normalization', 'SQL Joins', 'Primary Keys and Foreign Keys',
        'Entity-Relationship Model', 'Transaction Management', 'Indexing',
        'Concurrency Control', 'Data Independence', 'Relational Algebra',
        'Stored Procedures', 'Database Security', 'Query Optimization',
        'Database Schema Design', 'ACID Properties', 'Data Integrity Constraints',
    ],
    'python': [
        'List Comprehensions', 'Exception Handling', 'Decorators',
        'Generator Functions', 'Modules and Packages', 'Lambda Functions',
        'File Handling in Python', 'Regular Expressions', 'Iterators',
        'Dictionary Operations', 'String Manipulation', 'Virtual Environments',
        'Inheritance in Python', 'Error Handling', 'Python Data Types',
    ],
    'oop': [
        'Encapsulation', 'Inheritance', 'Polymorphism', 'Abstraction',
        'Design Patterns', 'SOLID Principles', 'Constructor Overloading',
        'Method Overriding', 'Composition versus Inheritance',
        'Interface Segregation', 'Dependency Injection', 'Observer Pattern',
        'Factory Pattern', 'Single Responsibility Principle', 'Cohesion and Coupling',
    ],
    'web': [
        'DOM Manipulation', 'CSS Flexbox and Grid', 'RESTful API Design',
        'AJAX and Fetch Requests', 'Session Management', 'HTTP Protocol',
        'Responsive Web Design', 'Cross-Origin Resource Sharing', 'Web Accessibility',
        'Single-Page Applications', 'Server-Side Rendering', 'Web Security',
        'Form Validation', 'Cookie Management', 'WebSocket Communication',
    ],
    'generic': [
        'Algorithm Analysis', 'Data Structures', 'System Design',
        'Security Principles', 'Performance Optimization', 'Modular Architecture',
        'Testing Strategies', 'Documentation Practices', 'Code Quality',
        'Project Management', 'Team Collaboration', 'Error Handling',
        'Resource Management', 'Scalability', 'Deployment Strategies',
    ],
}
# ── Cross-subject keyword filter ────────────────────────────────────
# Keywords strongly indicating a SPECIFIC subject. Used to reject topics
# that belong to ANOTHER subject (e.g. 'Data Models' in an SE paper).
_CROSS_SUBJECT_KW = {
    'database': [
        'database', 'sql', 'normalization', 'relational', 'er model',
        'entity relationship', 'primary key', 'foreign key', 'data model',
        'data redundancy', 'data independence', 'data dictionary', 'metadata',
        'concurrency control', 'transaction management', 'stored procedure',
        'tuple', 'schema', 'dbms', 'data integrity', 'query optimization',
        'er diagram', 'data dependence', 'file structure', 'file processing',
        'knowledge data', 'acid properties', 'indexing',
        # Broader DB terms that leaked in previous papers
        'semi-structured', 'semi structured', 'structured data',
        'unstructured data', 'manipulative part', 'manipulative',
        'entity', 'attribute', 'cardinality', 'associative',
        'record', 'records', 'filing', 'drawers', 'filing pocket',
        'data abstraction', 'data definition', 'dml', 'ddl', 'dcl',
        'relational algebra', 'functional dependency', 'decomposition',
        'super key', 'candidate key', 'composite key',
        'referential integrity', 'table', 'tablespace',
        'select query', 'insert query', 'delete query', 'update query',
        'er component', 'weak entity', 'strong entity',
        'scholar research', 'resid', 'schid',
        # Even broader terms to stop persistent leakage
        'data description', 'data descriptions', 'specialization hierarchy',
        'generalization hierarchy', 'is-a hierarchy',
        'the database', 'a database', 'in a database',
        'data types', 'data type', 'data sharing',
        'flat file', 'data warehouse', 'data mining',
        'data manipulation', 'relational model', 'hierarchical model',
        'network model', 'object-oriented database',
    ],
    'python': [
        'python', 'pip install', '__init__', 'virtualenv',
        'list comprehension', 'decorator', 'generator function',
    ],
    'oop': [
        'encapsulation', 'polymorphism', 'method overriding',
        'method overloading', 'abstract class', 'constructor overloading',
        'interface segregation',
    ],
    'web': [
        'html', 'css', 'javascript', 'dom manipulation', 'ajax',
        'rest api', 'http protocol', 'web server', 'responsive design',
    ],
    'se': [
        'requirements engineering', 'software testing', 'agile methodology',
        'waterfall model', 'scrum sprint', 'use case diagram',
        'risk management', 'configuration management', 'regression testing',
    ],
}
def _is_on_topic(text, subject):
    """Return True only if *text* does NOT contain keywords exclusive to OTHER subjects."""
    if not text or not subject:
        return True
    tl = text.lower()
    for other_subj, keywords in _CROSS_SUBJECT_KW.items():
        if other_subj == subject:
            continue
        for kw in keywords:
            if kw in tl:
                return False
    return True
def _clean_topic_phrase(topic):
    """Remove PDF artifacts: echoed/duplicate fragments, trailing noise."""
    if not topic:
        return topic
    # Fix "Duplication of data Same data" → "Duplication of data"
    # Detect when latter half echoes words from the first half
    words = topic.split()
    if len(words) >= 4:
        for split_pt in range(2, len(words)):
            left = ' '.join(words[:split_pt]).lower()
            right_first = words[split_pt].lower()
            # If a word from the right half already appeared in the left, truncate
            if right_first in left.split() and not right_first in ('of', 'and', 'the', 'in', 'a', 'to', 'for', 'with'):
                candidate = ' '.join(words[:split_pt])
                if len(candidate) >= 4:
                    return candidate
    return topic

def _pick_valid_topic(sentence, idx, subject):
    """Extract a validated, ON-TOPIC topic from a sentence, falling back to subject topic bank."""
    # Try concept extraction
    concept, _ = _extract_concept_from_sentence(sentence)
    if concept and _is_valid_topic(concept) and _is_on_topic(concept, subject):
        return _clean_topic_phrase(concept)
    # Try topic extraction
    topic = _extract_topic_from_sentence(sentence)
    if topic and _is_valid_topic(topic) and _is_on_topic(topic, subject):
        return _clean_topic_phrase(topic)
    # Fall back to subject topic bank (guaranteed clean + on-topic)
    bank = _APP_SUBJECT_TOPIC_BANKS.get(subject, _APP_SUBJECT_TOPIC_BANKS['generic'])
    return bank[idx % len(bank)]
def _extract_concept_from_sentence(sentence):
    """Try to extract a concept name from 'X is/refers to/means Y' patterns."""
    m = re.match(
        r'^\s*(.{2,60}?)\s+(?:is|are|was|were|refers?\s+to|means|describes?|involves?|'
        r'consists?\s+of|represents?|denotes?|can\s+be\s+defined\s+as|is\s+defined\s+as)\s+(.{12,})\s*$',
        sentence, re.I
    )
    if m:
        concept = m.group(1).strip().rstrip('.,;:')
        defn = m.group(2).strip().rstrip('.,;:')
        # Reject overly short/generic concepts
        if len(concept) < 3 or len(concept.split()) > 6 or not defn:
            return None, None
        # Reject pronouns, conjunctions, articles, question words as concepts
        _BAD_CONCEPT_WORDS = {
            'it', 'they', 'he', 'she', 'we', 'you', 'this', 'that', 'these',
            'those', 'there', 'here', 'but', 'and', 'or', 'so', 'yet', 'nor',
            'the', 'a', 'an', 'what', 'which', 'who', 'how', 'why', 'when',
            'where', 'also', 'however', 'although', 'because', 'but it',
            'and it', 'it also', 'they are', 'there are', 'here is',
        }
        concept_lower = concept.lower().strip()
        if concept_lower in _BAD_CONCEPT_WORDS:
            return None, None
        # Reject if concept starts with a pronoun/conjunction
        first_word = concept.split()[0].lower()
        if first_word in {'it', 'they', 'he', 'she', 'we', 'you', 'this', 'that',
                          'these', 'those', 'there', 'here', 'but', 'and', 'or',
                          'so', 'yet', 'nor', 'also', 'however', 'although'}:
            return None, None
        # Reject concepts that are all lowercase single words < 4 chars
        if len(concept) < 4 and concept == concept.lower():
            return None, None
        return concept, defn
    return None, None
def _extract_topic_from_sentence(sentence):
    """Extract a usable topic phrase from a sentence even when it's not a clean definition.
   
    Tries multiple strategies:
      1. Capitalized noun phrases (e.g. "Data Independence", "Program Data")
      2. Subject of the sentence (text before 'is/are/involves/refers')
      3. First meaningful multi-word phrase
    Returns a topic string or None.
    """
    if not sentence or len(sentence) < 8:
        return None
    s = sentence.strip()
    # Strategy 1: Extract Capitalized Noun Phrases (most reliable for academic text)
    cap_phrases = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', s)
    # Filter out common sentence starters
    _SKIP_STARTERS = {'The', 'This', 'That', 'These', 'Those', 'There', 'Each', 'Every',
                       'Some', 'Any', 'All', 'Most', 'Many', 'Several', 'Few', 'Both',
                       'In The', 'On The', 'At The', 'For The', 'By The', 'With The'}
    for cp in cap_phrases:
        if cp.split()[0] not in {'The', 'This', 'That', 'These', 'Those', 'There', 'Each',
                                  'Every', 'Some', 'Any', 'All', 'Most', 'Many', 'Several',
                                  'Few', 'Both', 'In', 'On', 'At', 'For', 'By', 'With'}:
            if 2 <= len(cp.split()) <= 5 and len(cp) > 4 and _is_valid_topic(cp):
                return cp
    # Strategy 2: Text before 'is/are/involves/refers to' (subject of definition sentence)
    m = re.match(
        r'^\s*(.{3,50}?)\s+(?:is|are|was|were|refers?\s+to|means|involves?|consists?\s+of|represents?)\s',
        s, re.I
    )
    if m:
        subj = m.group(1).strip().rstrip('.,;:')
        subj_lower = subj.lower()
        # Skip pronoun/generic subjects
        if subj_lower not in {'it', 'they', 'this', 'that', 'there', 'here', 'these', 'those',
                               'he', 'she', 'we', 'you', 'the system', 'the process'}:
            if len(subj) > 3 and len(subj.split()) <= 5 and _is_valid_topic(subj):
                return subj
    # Strategy 3: First noun-like phrase (words before first verb)
    words = s.split()
    if len(words) >= 3:
        # Take first 2-4 words if they form a reasonable topic
        candidate = ' '.join(words[:min(4, len(words))])
        candidate = re.sub(r'[.,;:!?\-]+$', '', candidate).strip()
        if len(candidate) > 5 and candidate[0].isupper() and _is_valid_topic(candidate):
            return candidate
    return None
# Dangling words that indicate a truncated sentence/fragment
_MCQ_DANGLE_WORDS = {
    'a', 'an', 'the', 'that', 'which', 'who', 'whom', 'whose',
    'and', 'or', 'but', 'if', 'as', 'by', 'to', 'of', 'in',
    'on', 'at', 'for', 'with', 'from', 'into', 'than', 'about',
    'when', 'where', 'while', 'although', 'because', 'since',
    'unless', 'until', 'after', 'before', 'whether', 'so',
    'those', 'these', 'them', 'they', 'its', 'their',
    'be', 'been', 'being', 'not', 'also', 'only', 'such',
    'some', 'every', 'each', 'any', 'all', 'is', 'are', 'was',
    'were', 'has', 'have', 'had', 'do', 'does', 'did', 'will',
    'can', 'may', 'shall', 'should', 'would', 'could', 'following',
    'between', 'among', 'through', 'during', 'within', 'without',
    'using', 'via', 'per', 'like', 'unlike', 'versus',
}
# Words that signal sentence-continuation fragments when they START an option
_MCQ_BAD_FIRST_WORDS = {
    # Conjunctions — indicate mid-paragraph continuation
    'but', 'and', 'or', 'yet', 'so', 'nor',
    # Conjunctive adverbs / transitions
    'however', 'although', 'nevertheless', 'furthermore', 'moreover',
    'additionally', 'hence', 'thus', 'therefore', 'meanwhile',
    'otherwise', 'consequently', 'similarly', 'likewise',
    # Question/interrogative words — options must be statements, not questions
    'why', 'how', 'what', 'when', 'where', 'which', 'who', 'whom',
}
# Bullet/arrow/special characters that indicate raw slide content
_MCQ_BULLET_CHARS = set('\u25aa\u25cf\u2022\u25ab\u2023\u00bb\u25a0\u25c6'
                         '\u25e6\u25ba\u27a2\u27a4\u279c\u2794\u27a1\u25b9'
                         '\u276f\u2756\u2666\u25c7\u2500\u254c\u00b0\u25b6'
                         '\u2192\u2218\u2611\u2610\u25b8\u203a\u2713')
def _valid_mcq_option(text):
    """Check if a text string is suitable as an MCQ option.
    Must be a complete, clean sentence/phrase — not a truncated fragment.
    """
    if not text or not isinstance(text, str):
        return False
    s = text.strip()
    if len(s) < 15:
        return False # too short
    # Reject if starts with punctuation (comma, semicolon, etc.)
    if s[0] in ',;.!?-–—/':
        return False
    # Reject if starts with a digit or digit+letter artifact like "26A"
    if re.match(r'^\d', s):
        return False
    # Reject if contains bullet/arrow chars
    if any(c in s for c in _MCQ_BULLET_CHARS):
        return False
    # Reject if contains math/formula chars
    if re.search(r'[×÷∑∫∂∈∉∀∃{}\[\]<>]', s):
        return False
    # Reject if has unmatched parentheses like "D1 × D2 × D3 = {(1,2,5)"
    if s.count('(') != s.count(')') or s.count('{') != s.count('}'):
        return False
    words = s.split()
    if len(words) < 5:
        return False # less than 5 words — too short for a meaningful option
    if len(words) > 28:
        return False # absurdly long
    # Last word must NOT be a dangling preposition/conjunction/article
    last_word = words[-1].lower().rstrip('.,;:?!')
    if last_word in _MCQ_DANGLE_WORDS:
        return False
    # Must not end with comma (truncated)
    if s.rstrip().endswith(',') or s.rstrip().endswith('('):
        return False
    # Must not start with lowercase (fragment continuation)
    if s[0].islower():
        return False
    # Reject if starts with a pronoun (vague slide fragment like "It is used...")
    first_word = words[0].lower().rstrip('.,;:?!')
    if first_word in {'it', 'they', 'he', 'she', 'we', 'its', 'their', 'them',
                       'this', 'these', 'those', 'simply', 'basically', 'actually'}:
        return False
    # Reject if first word is a conjunction, transition, or question word
    if first_word in _MCQ_BAD_FIRST_WORDS:
        return False
    # Reject headings (ALL words capitalized, no verb, short)
    if len(words) <= 6 and s == s.title() and ':' not in s:
        return False
    # Reject lines that look like labels "Something: -value" or "Term:" or "Data: definition"
    if re.match(r'^[\w\s]+:\s*$', s) or re.match(r'^[\w\s]+:\s*-', s):
        return False
    # Reject slide-style label:definition patterns like "Data: known facts that..."
    if re.match(r'^[A-Z][a-z]{1,20}:\s+[a-z]', s):
        return False
    # Reject multi-word label:pronoun like "Procedural DML: It allows..."
    if re.match(r'^[A-Z][\w\s]{1,40}:\s+(It|They|This|These|Those|He|She|We)\b', s):
        return False
    # Reject if contains "etc" at the end (incomplete list)
    if re.search(r'\betc\.?\s*$', s, re.I):
        return False
    # Reject slide-style fragments: "There are following X" or "Following are the X"
    if re.match(r'^There\s+are\s+following\b', s, re.I):
        return False
    if re.match(r'^Following\s+are\b', s, re.I):
        return False
    # Reject "X of Y" noun-phrase fragments with no verb ("Set of relation schemas")
    if re.match(r'^[A-Z][a-z]+\s+of\s+', s) and len(words) <= 8 and not re.search(r'\b(is|are|was|were|has|have|provides|allows|ensures|includes|defines|requires|involves|means|contains)\b', s, re.I):
        return False
    # Reject doubled conjunctions like "stores and students and course"
    sl = s.lower()
    if re.search(r'\band\b.*\band\b.*\band\b', sl) or re.search(r'\bor\b.*\bor\b.*\bor\b', sl):
        return False
    # Reject "and X and" pattern (double and with short gap — grammatically broken)
    if re.search(r'\band\s+\w+\s+and\b', sl):
        return False
    # Reject space-hyphen PDF artifacts like "end -users" or "non -standard"
    if re.search(r'\w\s+-[a-z]', s):
        return False
    # Reject physical-filing / non-academic descriptions
    _PHYSICAL_WORDS = {'drawers', 'pockets', 'filing cabinet', 'paper files',
                        'cardboard', 'folders', 'binder', 'shelf'}
    if sum(1 for pw in _PHYSICAL_WORDS if pw in sl) >= 2:
        return False
    # Must have at least one verb-like word (basic completeness check)
    _VERB_INDICATORS = re.compile(
        r'\b(is|are|was|were|has|have|had|does|do|did|can|could|will|would|'
        r'shall|should|may|might|must|need|used|allows|enables|provides|'
        r'defines|stores|represents|includes|consists|ensures|prevents|'
        r'reduces|improves|manages|controls|handles|specifies|describes|'
        r'maintains|performs|requires|involves|refers|means|supports|'
        r'creates|implements|processes|operates|functions|serves|'
        r'identifies|determines|organizes|facilitates|generates|'
        r'eliminates|restricts|permits|contains|establishes|'
        r'stored|defined|shared|organized|structured|related|designed|'
        r'used|applied|called|known|based|kept|made|held|given|set|run|led)\b', re.I
    )
    if not _VERB_INDICATORS.search(s):
        return False
    return True
# ═══════════════════════════════════════════════════════════════════════
# Subject-adaptive MCQ pools — keywords, correct fallbacks, wrong pools
# ═══════════════════════════════════════════════════════════════════════
_SUBJECT_KEYWORDS = {
    'database': ['database', 'dbms', 'sql', 'table', 'query', 'normalization', 'primary key',
                 'foreign key', 'relational', 'index', 'transaction', 'er diagram', 'schema',
                 'acid', 'join', 'select', 'stored procedure', 'trigger', 'view', 'tuple'],
    'python': ['python', 'def ', 'lambda', 'list comprehension', 'dictionary', 'tuple',
                 'decorator', 'generator', 'pip', 'numpy', 'pandas', 'flask', 'django',
                 'indentation', 'exception', 'class', 'self', '__init__', 'module', 'import'],
    'oop': ['object-oriented', 'oop', 'inheritance', 'polymorphism', 'encapsulation',
                 'abstraction', 'class diagram', 'method overriding', 'method overloading',
                 'interface', 'abstract class', 'constructor', 'destructor', 'uml',
                 'composition', 'aggregation', 'coupling', 'cohesion', 'design pattern'],
    'web': ['html', 'css', 'javascript', 'react', 'angular', 'vue', 'dom',
                 'responsive', 'bootstrap', 'node.js', 'express', 'api', 'rest', 'json',
                 'ajax', 'http', 'frontend', 'backend', 'full stack', 'web server',
                 'session', 'cookie', 'web application', 'url', 'web browser', 'markup',
                 'web page', 'php', 'servlet', 'web development'],
    'se': ['software engineering', 'sdlc', 'agile', 'scrum', 'waterfall', 'requirement',
                 'use case', 'testing', 'unit test', 'integration test', 'deployment',
                 'version control', 'git', 'ci/cd', 'software design', 'maintenance',
                 'spiral model', 'prototype', 'risk management', 'software process'],
}
def _detect_subject(source_text):
    """Return the best-matching subject key using DistilBERT classifier first,
    falling back to keyword frequency when the model is unavailable."""
    if not source_text:
        return 'generic'
    # ── 1. Try DistilBERT subject classifier (most accurate) ─────────
    _DISTILBERT_TO_POOL = {
        'python_programming_basics': 'python',
        'database_fundamentals': 'database',
        'web_development': 'web',
        'software_engineering': 'se',
        'oop_basics': 'oop',
    }
    try:
        result = classify_subject(source_text[:3000])
        if result and result.get('confidence', 0) >= 0.45:
            mapped = _DISTILBERT_TO_POOL.get(result['subject'])
            if mapped:
                logger.debug("Subject detection: DistilBERT → %s (conf=%.2f)", mapped, result['confidence'])
                return mapped
    except Exception as exc:
        logger.debug("Subject detection: DistilBERT failed: %s", exc)
    # ── 2. Fallback: keyword frequency ───────────────────────────────
    sample = source_text[:5000].lower()
    best, best_count = 'generic', 0
    for subj, kws in _SUBJECT_KEYWORDS.items():
        count = sum(1 for kw in kws if kw in sample)
        if count > best_count:
            best, best_count = subj, count
    detected = best if best_count >= 3 else 'generic'
    logger.debug("Subject detection: keyword → %s (hits=%d)", detected, best_count)
    return detected

# Map QG-style subject keys back to pool keys used by _CORRECT_POOLS / _WRONG_POOLS
_QG_TO_POOL_KEY = {
    'database_fundamentals': 'database',
    'python_programming': 'python',
    'object_oriented_programming': 'oop',
    'web_development': 'web',
    'software_engineering': 'se',
    'general': 'generic',
}
def _pool_key(subject):
    """Resolve any subject variant to the pool key used by _CORRECT_POOLS / _WRONG_POOLS."""
    if not subject:
        return 'generic'
    s = subject.lower()
    return _QG_TO_POOL_KEY.get(s, s)

_CORRECT_POOLS = {
    'database': [
        'A well-designed database reduces redundancy and improves data consistency',
        'A DBMS provides controlled access to data through security and authorization mechanisms',
        'Data independence allows changes to storage structure without affecting application programs',
        'Normalization reduces data redundancy by organizing tables based on functional dependencies',
        'A primary key uniquely identifies each record in a database table',
        'Referential integrity ensures that foreign key values match existing primary key values',
        'A relational database organizes data into tables with rows and columns linked by keys',
        'Transaction processing ensures atomicity so that partial updates never persist',
        'Indexes speed up data retrieval by providing direct access paths to specific records',
        'Concurrency control prevents conflicts when multiple users access the same data simultaneously',
        'A view is a virtual table derived from one or more base tables using a stored query',
        'The three-schema architecture separates external, conceptual, and internal levels of a database',
        'Stored procedures encapsulate reusable SQL logic that executes on the database server',
        'A trigger is a stored routine that fires automatically in response to specific table events',
        'Denormalization intentionally introduces redundancy to improve read performance in large systems',
    ],
    'python': [
        'Python uses indentation to define code blocks instead of curly braces',
        'A list comprehension provides a concise way to create lists from existing iterables',
        'Decorators allow you to modify the behavior of a function without changing its source code',
        'Generators use yield to produce a sequence of values lazily, saving memory',
        'Exception handling with try-except blocks prevents programs from crashing on runtime errors',
        'Dictionaries store data as key-value pairs and provide fast lookup by key',
        'The self parameter in a method refers to the current instance of the class',
        'Modules allow you to organize Python code into reusable files that can be imported',
        'Tuples are immutable sequences that cannot be modified after creation',
        'Lambda functions are anonymous single-expression functions defined with the lambda keyword',
        'Python supports multiple inheritance allowing a class to inherit from more than one parent',
        'The Global Interpreter Lock ensures only one thread executes Python bytecode at a time',
        'Context managers use the with statement to handle resource setup and cleanup automatically',
        'Slicing allows you to extract subsequences from lists and strings using start stop and step',
        'The itertools module provides efficient looping constructs for combinatoric iteration patterns',
    ],
    'oop': [
        'Encapsulation bundles data and methods together while restricting direct access to internal state',
        'Inheritance allows a child class to reuse and extend the behavior of a parent class',
        'Polymorphism enables objects of different classes to respond to the same method call differently',
        'Abstraction hides implementation details and exposes only the essential features to users',
        'A constructor initializes an object state when a new instance of a class is created',
        'Method overriding allows a subclass to provide its own implementation of a parent method',
        'Composition models a has-a relationship where one object contains instances of other objects',
        'Coupling measures how strongly one class depends on other classes in the system',
        'Cohesion measures how closely the methods in a class are related to a single purpose',
        'An interface defines a contract of methods that implementing classes must provide',
        'The Liskov Substitution Principle states that a subclass should be usable wherever its parent is expected',
        'An abstract class provides partial implementation and cannot be instantiated on its own',
        'The Single Responsibility Principle says a class should have only one reason to change',
        'Dependency injection supplies objects with their collaborators rather than letting them create dependencies',
        'Design patterns are reusable solutions to commonly occurring problems in object-oriented design',
    ],
    'web': [
        'HTML provides the structural markup for web pages using elements and attributes',
        'CSS controls the visual presentation and layout of HTML elements on a web page',
        'JavaScript enables interactive behavior and dynamic content updates in web browsers',
        'The DOM represents the HTML document as a tree of nodes that can be manipulated programmatically',
        'Responsive design ensures web pages adapt their layout to different screen sizes and devices',
        'HTTP is the protocol used for communication between web browsers and web servers',
        'RESTful APIs use standard HTTP methods to perform CRUD operations on server resources',
        'Session management allows web applications to maintain user state across multiple requests',
        'AJAX enables asynchronous data exchange with a server without reloading the entire page',
        'A web server processes incoming HTTP requests and returns appropriate responses to clients',
        'CORS policies control which external domains are allowed to access resources from a web server',
        'Single-page applications load one HTML page and update content dynamically via JavaScript',
        'Web sockets provide full-duplex communication channels between a browser and a server',
        'Content Delivery Networks cache static assets at edge locations to reduce page load times',
        'Server-side rendering generates the initial HTML on the server before sending it to the browser',
    ],
    'se': [
        'The software development life cycle defines phases from requirements gathering to maintenance',
        'Agile methodology emphasizes iterative development with frequent customer feedback and collaboration',
        'Requirements engineering captures what the system should do before design and implementation begin',
        'Unit testing verifies that individual components of the software work correctly in isolation',
        'Version control systems track changes to source code and enable team collaboration over time',
        'The waterfall model follows a sequential approach where each phase must complete before the next begins',
        'Software maintenance includes corrective, adaptive, perfective, and preventive activities after deployment',
        'Risk management identifies potential problems early and plans mitigation strategies for each risk',
        'Integration testing verifies that different modules of a system work together correctly as a group',
        'A use case describes a sequence of interactions between a user and the system to achieve a goal',
        'Continuous integration merges developer code changes into a shared repository multiple times a day',
        'Code refactoring improves internal structure without changing the external behavior of the software',
        'The spiral model combines iterative development with systematic risk analysis at every phase',
        'Configuration management tracks and controls changes to software artifacts throughout the lifecycle',
        'Software metrics provide quantitative measures for evaluating process efficiency and product quality',
    ],
    'generic': [
        'A well-structured explanation should include definitions, examples, and supporting evidence',
        'Critical analysis involves evaluating the strengths and limitations of different approaches',
        'Effective problem solving requires breaking complex issues into smaller manageable components',
        'Theory provides the foundational principles that guide practical application in real scenarios',
        'Comparing different approaches reveals the trade-offs between complexity, cost, and effectiveness',
        'Documentation helps maintain knowledge continuity and supports future maintenance efforts',
        'Best practices are proven methods that consistently produce reliable and efficient outcomes',
        'Systematic evaluation of alternatives leads to more informed and objective decision-making',
        'Standards and guidelines ensure consistency and quality across complex systems and processes',
        'Fundamental concepts serve as building blocks for understanding advanced topics in any discipline',
        'Modular design divides a system into independent components that can be developed and tested separately',
        'Abstraction reduces complexity by hiding unnecessary details and exposing only relevant interfaces',
        'Iterative improvement refines a solution through repeated cycles of evaluation and modification',
        'Validation confirms that the final product meets the needs and expectations of its intended users',
        'Traceability links each requirement to its corresponding design element and test case for accountability',
    ],
}
_WRONG_POOLS = {
    'database': [
        'Storing all records in a single flat file without any organized schema or access control',
        'Allowing every user to directly modify raw data without any validation or management layer',
        'Using no indexing strategy and performing sequential scans for every data retrieval request',
        'Keeping all data in memory without any persistent storage mechanism or backup procedure',
        'Requiring manual recalculation of all derived values whenever the underlying data changes',
        'Eliminating all constraints to maximize data entry speed regardless of accuracy or consistency',
        'Granting unrestricted write access to all tables without any authentication or user roles',
        'Performing every query by scanning the entire dataset from beginning to end sequentially',
        'Relying on application programs to enforce all data consistency rules manually without DBMS support',
        'Defining no relationships between entities and treating all data as completely independent rows',
        'Maintaining no backup or recovery procedure and accepting permanent data loss as a risk',
        'Storing each attribute in a separate file with no linking mechanism between related records',
        'Duplicating all records across separate files with no mechanism to ensure data consistency',
        'Allowing applications to bypass all security measures by directly editing data files on disk',
        'Treating every data retrieval request as a new connection with no caching or query optimization',
        'Ignoring data types entirely and storing everything as unstructured plain text without validation',
        'Processing all database queries in a fixed sequential order regardless of priority or urgency',
        'Requiring every user to write raw machine code to retrieve or update any database record',
        'Implementing each table as a completely independent entity with no foreign key relationships',
        'Hardcoding all data validation rules inside each individual application program separately',
        'A foreign key must always reference the same table in which it is originally defined',
        'Primary keys are optional for database tables and are only recommended for very large datasets',
        'Data redundancy is always beneficial in databases because it consistently improves query performance',
        'Denormalization always produces better overall results than any normalized database design approach',
        'A view in a database creates a permanent physical copy of the data in a new separate table',
        'Concurrency control mechanisms are only necessary when more than one hundred users access the data',
        'Normalization always requires splitting every table into the smallest possible atomic fragments',
        'A database schema cannot be modified or updated once the database has been populated with data',
        'Keeping all metadata mixed with actual data so that structure cannot be identified separately',
        'Removing all indexes from a database to reduce storage space regardless of query performance impact',
        'Storing sensitive passwords in plain text within the database without any encryption mechanism',
        'Allowing any user to drop or truncate production tables without requiring special privileges',
        'Using a single shared login account for every database user regardless of their role or permissions',
        'Bypassing transaction logs entirely to achieve faster write speeds at the cost of recoverability',
        'Embedding raw SQL statements directly in client-side browser code without server-side validation',
        'Assigning the same primary key value to multiple rows in the same table intentionally',
        'Treating null values and empty strings as identical in all query comparisons and constraints',
        'Removing all foreign key constraints to allow faster bulk inserts regardless of data integrity',
        'Designing every database table with a single column that stores all attributes as concatenated text',
        'Replicating the full database to every client device without any synchronization or conflict resolution',
        'Assuming that data entered by end users is always correct and never requires validation checks',
        'Placing every stored procedure and trigger in a single monolithic script without modular design',
        'Disabling all logging and audit trails to minimize storage usage in a production environment',
        'Using sequential full-table scans as the only query strategy regardless of available indexes',
        'Giving every column the same generic name across all tables to simplify the schema design',
        'Running all database maintenance tasks manually during peak usage hours without scheduling',
        'Storing binary large objects inline with transaction data in the same row without external storage',
        'Defining all columns as variable-length text fields regardless of the actual data requirements',
        'Granting permanent superuser privileges to temporary accounts used only for one-time data migration',
        'Merging all entity types into one universal table with hundreds of nullable columns for every attribute',
        'Deleting old records by overwriting them with blank values instead of using proper delete operations',
        'Returning the entire contents of a table to the application layer and filtering results in memory',
        'Locking the entire database for every single read query regardless of which tables are accessed',
        'Storing date and time values as plain unformatted text strings without any standard format',
        'Creating a separate physical database for every individual user instead of using access controls',
        'Writing all business logic directly inside database triggers with no external documentation',
    ],
    'python': [
        'Python requires semicolons at the end of every line or the code will not execute',
        'Variables in Python must be declared with an explicit type before they can be used',
        'Python does not support object-oriented programming and only allows procedural coding',
        'Lists and tuples are identical data structures with no difference in behavior or mutability',
        'Exception handling is not available in Python and all errors must be prevented manually',
        'Python dictionaries maintain elements in alphabetical order by key at all times',
        'The global keyword is required every time a variable is used inside any function body',
        'Indentation in Python is purely cosmetic and has no effect on program logic or structure',
        'Lambda functions in Python can contain multiple statements and complex control flow logic',
        'Python modules cannot be imported once they are saved to disk as separate files',
        'Generators produce all values at once and store them in memory before returning the result',
        'Decorators permanently modify the original function and cannot be removed or reversed once applied',
        'List comprehension executes slower than a regular for-loop in every possible scenario',
        'Python only supports single inheritance and does not allow a class to inherit from multiple parents',
        'The pass statement terminates the program immediately when encountered during execution',
        'String concatenation with the plus operator is the only way to combine strings in Python',
        'Python cannot handle file operations and requires external tools for any file reading or writing',
        'Recursive functions are not supported in Python and will always cause a compilation error',
        'The range function generates a list of floating point numbers by default in Python 3',
        'Python functions cannot return multiple values and are limited to a single return statement',
        'Type conversion in Python must always be done manually with custom conversion functions',
        'All Python programs must contain a main function or they will not execute at all',
        'Python virtual environments have no effect and packages are always installed globally',
        'The with statement in Python only works for file operations and has no other uses',
        'Dictionary keys in Python can be mutable objects such as lists and other dictionaries',
        'Importing a module multiple times causes the code in that module to execute each time',
        'Python does not support default parameter values in function definitions at all',
        'Sets in Python maintain insertion order and allow duplicate elements to be stored',
        'The elif keyword in Python is just a comment and has no effect on conditional logic',
        'Python strings are mutable and individual characters can be changed by index assignment',
        'The map function modifies the original list in place rather than returning a new iterator',
        'Slicing a list in Python always creates a deep copy of all nested objects within it',
        'Python does not support multiple assignment and each variable must be assigned separately',
        'The __name__ variable is always set to __main__ regardless of how the module is executed',
        'Python 3 removed support for classes entirely and only allows standalone functions',
        'The try block must always be followed by both except and finally or it will cause an error',
        'Python integers have a fixed maximum size and will overflow if they exceed that limit',
        'The print function in Python 3 is a statement and not a callable function object',
        'Global variables are always preferred over local variables for better code organization',
        'The None keyword in Python is identical to zero and can be used in arithmetic operations',
        'Python closures cannot access variables from their enclosing function scope at all',
        'The zip function permanently merges two lists into a single combined list object',
        'Abstract base classes are not supported in Python and only exist in statically typed languages',
        'The property decorator has no effect on attribute access and only serves as documentation',
        'Python context managers can only be used with file operations and nothing else',
        'Unpacking operators like * and ** only work inside print statements in Python 3',
        'The super function in Python always skips exactly one level in the inheritance hierarchy',
        'Python f-strings execute all expressions at import time rather than at runtime evaluation',
        'Using * in a function signature prevents the function from accepting any arguments at all',
        'The collections module provides no additional data structures beyond the built-in types',
        'Python asyncio makes every function run in parallel on separate CPU cores automatically',
        'Type hints in Python are enforced at runtime and will raise errors for type mismatches',
        'The enumerate function only works with lists and cannot be used with other iterables',
        'Python garbage collection must be triggered manually or memory will never be freed',
    ],
    'oop': [
        'Encapsulation means that all class attributes must always be publicly accessible to any code',
        'Inheritance forces the child class to override every single method defined in the parent class',
        'Polymorphism requires all classes to have exactly the same number of methods and attributes',
        'Abstraction means removing all methods from a class and keeping only the data attributes',
        'A constructor is only called when an object is destroyed, not when it is first created',
        'Method overloading and method overriding are identical concepts with no practical difference',
        'Composition is impossible in object-oriented programming and only inheritance can relate objects',
        'High coupling between classes is always desirable because it improves system flexibility',
        'Cohesion means distributing all related methods randomly across many different unrelated classes',
        'An abstract class can be instantiated directly without implementing any of its abstract methods',
        'Interfaces can contain full method implementations and private instance variables by default',
        'Multiple inheritance always causes errors and is never supported in any programming language',
        'Design patterns are rigid templates that must be applied identically in every single project',
        'A destructor is called automatically before the constructor when an object is being created',
        'Static methods require an instance of the class to be created before they can be called',
        'The Singleton pattern ensures that a class always creates a new instance for every request',
        'Loose coupling means that every class should directly access the private fields of other classes',
        'The Liskov Substitution Principle states that parent classes should always replace child classes',
        'All classes in a well-designed system should inherit from a single universal base class',
        'Aggregation means the contained object cannot exist independently of the container object',
        'Access modifiers like private and protected have no effect on the visibility of class members',
        'Object-oriented design always produces slower programs than procedural programming in every case',
        'UML class diagrams are only used after implementation is complete and never during design phases',
        'Dependency injection increases tight coupling by hardcoding all object creation inside classes',
        'A class should have as many responsibilities as possible to minimize the total number of classes',
        'Operator overloading requires rewriting the entire class from scratch for each operator defined',
        'Virtual methods prevent subclasses from providing their own implementation of that method',
        'An object can only belong to one class and cannot implement multiple interfaces simultaneously',
        'The Open-Closed Principle states that classes should be closed for extension and open for modification',
        'An interface and an abstract class are completely identical and interchangeable in every situation',
        'The Factory pattern eliminates all constructors and makes object creation completely impossible',
        'Getter and setter methods serve no purpose and should never be used in well-designed classes',
        'The this keyword in a method always refers to the parent class rather than the current object',
        'Final classes can still be extended by any subclass regardless of the final modifier',
        'Shallow copy and deep copy always produce identical results with no difference in behavior',
        'Method signatures have no role in method overloading and only the method body matters',
        'The Observer pattern requires all observers to poll the subject continuously in an infinite loop',
        'Protected members are accessible from any class in any package without any restrictions at all',
        'Generic types provide no type safety benefits and only make the code more difficult to read',
        'The Strategy pattern hardcodes all algorithm variants directly into a single monolithic class',
        'Downcasting is always safe and never requires any type checking before performing the cast',
        'The MVC pattern combines all model view and controller logic into a single class for simplicity',
        'Object serialization permanently destroys the original object and it cannot be reconstructed',
        'Inner classes have no access to the outer class members and function as completely independent units',
        'The Template Method pattern requires subclasses to rewrite the entire algorithm from scratch',
        'Late binding always causes runtime errors and should be replaced with early binding in all cases',
        'Association and dependency are identical relationships with no semantic difference between them',
        'A pure virtual function must contain a default implementation in the base class to be valid',
        'The Decorator pattern permanently modifies the original object and removes all its previous behavior',
        'Exception handling in OOP should be avoided entirely because it breaks the normal flow of control',
        'Package private access means the member is accessible from every package in the entire application',
        'Abstract methods can have a complete implementation body and still be marked as abstract',
        'The Bridge pattern tightly couples abstraction and implementation so they cannot vary independently',
        'Garbage collection in OOP requires the programmer to manually free every object after use',
    ],
    'web': [
        'HTML is a programming language that can perform calculations and complex logic operations',
        'CSS can directly modify the database and change server-side data without any backend code',
        'JavaScript only runs on the server and cannot execute in a web browser environment',
        'The DOM is a static structure that cannot be modified after the web page has been loaded',
        'Responsive design means creating a separate complete website for every possible screen size',
        'HTTP is a stateful protocol that automatically remembers all previous requests from a client',
        'RESTful APIs require a persistent connection between the client and server at all times',
        'Cookies are stored on the server and cannot be accessed or managed by the web browser',
        'AJAX requires a full page reload every time data is exchanged with the server',
        'A web server only handles static HTML files and cannot process any dynamic content at all',
        'HTML forms can directly write data to a database without any server-side processing',
        'CSS media queries have no effect on how a web page appears on different screen sizes',
        'Session data is stored in the browser URL and is visible to all users on the network',
        'JSON is a binary data format that cannot be read or edited by humans directly',
        'Web browsers send requests using the FTP protocol by default for all web page navigation',
        'The same-origin policy allows any website to freely access data from any other website domain',
        'Server-side rendering means that all processing is done in the browser after page load',
        'HTTPS provides no security benefits over HTTP and only slows down the website connection',
        'Web sockets are identical to standard HTTP requests and offer no additional capabilities',
        'PHP can only be used for static web pages and does not support any server-side processing',
        'URL parameters are always encrypted and cannot be seen by users or intermediary servers',
        'Bootstrap is a backend framework that handles database operations and server-side logic',
        'Single-page applications require the entire page to reload for every navigation action',
        'Client-side validation alone is sufficient to guarantee data security on any web application',
        'Web accessibility standards only apply to government websites and not to commercial applications',
        'The viewport meta tag has no effect on how mobile devices render and display web pages',
        'All modern web browsers interpret and render HTML and CSS in exactly the same way',
        'DNS resolution is only performed once and the result is permanently cached for all future visits',
        'CSS flexbox and grid layouts are identical and provide no distinct advantages over each other',
        'The localStorage API shares data between all websites on the same browser without restrictions',
        'Web workers execute on the main thread and will always block the user interface during execution',
        'Cross-site scripting can only occur on websites that use JavaScript frameworks like React or Angular',
        'The HTTP DELETE method permanently removes the web server itself rather than a specific resource',
        'Content Delivery Networks have no effect on website loading speed or availability for end users',
        'GraphQL replaces all databases and eliminates the need for any server-side data storage entirely',
        'The fetch API in JavaScript can only send GET requests and does not support POST or PUT methods',
        'Progressive web applications require a native app store listing before they can be installed',
        'Server-sent events and AJAX polling provide identical performance and resource usage in all cases',
        'The Content-Type header has no effect on how the server or browser processes the HTTP response',
        'CORS is an attack vector that should be disabled on all production servers for maximum security',
        'Minifying JavaScript and CSS files increases their size and has no effect on page load performance',
        'WebAssembly completely replaces JavaScript and all new web applications must use it exclusively',
        'HTML semantic elements like nav and article have no effect on search engine optimization at all',
        'The service worker API only works on desktop browsers and provides no benefits for mobile users',
        'HTTP status code 404 means the server crashed and all services on that server are unavailable',
        'All REST API endpoints must return XML format and JSON is not a valid response format for APIs',
        'Web fonts must be installed on every user computer before they can appear on any web page',
        'Template engines process all templates on the client side and never involve the server',
        'Rate limiting on web APIs serves no security purpose and only frustrates legitimate users',
        'OAuth authentication stores the user password directly in the browser cookies for later use',
        'IndexedDB in the browser provides the same full SQL query language as a traditional database',
        'The HTTP OPTIONS request method is only used for debugging and should be blocked in production',
        'Lazy loading images increases initial page load time because all images must still load at once',
        'A reverse proxy serves static files directly to clients without providing any caching or security',
    ],
    'se': [
        'The waterfall model encourages going back to previous phases whenever new requirements emerge',
        'Agile methodology requires completing all documentation before any coding can begin at all',
        'Requirements engineering is only performed after the software has been fully coded and tested',
        'Unit testing verifies the complete integrated system rather than individual isolated components',
        'Version control systems only store the latest version and discard all previous file histories',
        'Software maintenance is never needed once the software has been successfully deployed to production',
        'Risk management is only performed at the very end of the project after all coding is complete',
        'Integration testing checks individual functions in isolation rather than interactions between modules',
        'A use case diagram shows the internal implementation details of every class in the system',
        'The spiral model follows a strict linear sequence with no iterations or risk analysis phases',
        'Scrum sprints have no fixed time duration and can continue for as long as the team wishes',
        'Continuous integration means manually uploading code to the server once every few months',
        'Software prototyping delays the project because users never provide useful feedback on prototypes',
        'Acceptance testing is performed by the development team without any involvement from the customer',
        'Configuration management only tracks documentation and does not apply to source code changes',
        'Code reviews provide no benefit because automated testing catches every possible software defect',
        'Software quality assurance activities are only performed during the final testing phase of the project',
        'The V-model does not include testing phases and focuses entirely on development activities only',
        'Design patterns are only used during maintenance and have no role in initial software design',
        'Pair programming reduces productivity because two developers on one task always wastes resources',
        'Software metrics are subjective opinions that cannot be measured or quantified in any way',
        'Functional requirements describe non-technical constraints like budget, schedule, and team size',
        'System testing is identical to unit testing and both verify the same scope of functionality',
        'The product backlog in Scrum is finalized at the start and cannot be changed during the project',
        'Regression testing is only needed when adding new features and not when fixing existing bugs',
        'Software architecture decisions are trivial and have no long-term impact on system quality',
        'Load testing verifies the visual appearance of the user interface across different web browsers',
        'Technical debt has no real consequences and can be safely ignored throughout the entire project',
        'The Kanban method requires all work items to be completed in a strict predetermined sequence',
        'Software estimation is unnecessary because experienced developers always know exactly how long tasks take',
        'Refactoring changes the external behavior of the software while keeping the internal design the same',
        'Stakeholder analysis is only relevant for government projects and not for commercial software development',
        'White-box testing requires no knowledge of the internal code and tests only external behavior',
        'Black-box testing examines the source code line by line to find implementation-level defects',
        'The Rational Unified Process has only one phase and does not support iterative development at all',
        'Software reuse always introduces more defects than writing completely new code from scratch',
        'Non-functional requirements like performance and security are only considered during the testing phase',
        'Change management is unnecessary when agile methods are used because agile welcomes all changes freely',
        'Code coverage of one hundred percent guarantees that the software contains absolutely no defects',
        'The project manager is the only person responsible for writing all requirements in every project',
        'Alpha testing is conducted by end users in the production environment after the product is released',
        'Beta testing is performed by the development team inside the company before any external users see it',
        'Feasibility studies are only performed after the system has been fully implemented and deployed',
        'Coupling between modules should be maximized to ensure better communication and data sharing',
        'The incremental model delivers the entire system at once with no intermediate partial releases',
        'Data flow diagrams show the sequence of events over time rather than the flow of data through processes',
        'Software verification ensures the product meets user needs while validation checks technical correctness',
        'Test-driven development requires writing all tests after the implementation is completely finished',
        'The COCOMO model estimates software cost based solely on the number of developers assigned to the project',
        'Deployment diagrams show the logical class structure and have nothing to do with physical hardware',
        'Extreme Programming discourages customer involvement and relies entirely on developer assumptions',
        'A software baseline can be changed by any team member at any time without formal approval',
        'Security testing is optional for internal enterprise applications that are not exposed to the internet',
        'The waterfall model is always the best choice for projects where requirements are uncertain and evolving',
    ],
    'generic': [
        'All theoretical concepts are purely abstract and have no practical application in real scenarios',
        'Memorizing definitions without understanding is the most effective approach to mastering any topic',
        'Complex problems should always be addressed as a single large task without any decomposition',
        'Best practices are arbitrary suggestions that provide no measurable improvement in any outcome',
        'Documentation is unnecessary when the system is well-designed because code is always self-explanatory',
        'Systematic analysis provides no advantage over random guessing when evaluating complex alternatives',
        'Standards and guidelines only add bureaucratic overhead without providing any real quality benefits',
        'Fundamental concepts have no connection to advanced topics and can be safely skipped by beginners',
        'All evaluation criteria are equally important regardless of the context or specific project needs',
        'Collaboration between team members always reduces overall productivity compared to working alone',
        'Quantitative data is irrelevant for decision-making because qualitative opinions are always sufficient',
        'Historical evidence and established research have no relevance to solving modern complex problems',
        'A single perspective is always adequate for understanding any multifaceted issue or decision',
        'Planning ahead provides no benefit because implementation details cannot be anticipated in advance',
        'Proper testing and validation methods are optional and do not affect outcome quality or reliability',
        'Feedback loops serve no purpose in iterative processes and should be eliminated for efficiency',
        'All problems have exactly one correct solution regardless of the context or constraints involved',
        'Simplicity in design always means removing important features until nothing useful remains',
        'Incremental improvement is ineffective and only radical complete redesigns produce positive results',
        'Expert domain knowledge is unnecessary because general-purpose approaches always work equally well',
        'Maintaining organized records provides no benefit for future reference or long-term project success',
        'Ignoring edge cases is acceptable when the main functionality appears to be working correctly',
        'Ethical considerations are irrelevant when the technical solution achieves the desired outcome',
        'Peer review has no value because individuals always produce better results working independently',
        'Automating repetitive processes provides no improvement over performing each step manually every time',
        'Communication skills have no impact on the success of technical projects or team-based work',
        'Scalability concerns should only be addressed after a system has completely failed under real load',
        'Preventive measures are wasteful because it is always cheaper to fix problems after they occur',
        'Accuracy is irrelevant when the result is produced quickly because speed always outweighs correctness',
        'Formal training provides no advantage over random experimentation when learning complex new skills',
        'Risk assessment is unnecessary because unexpected events can never be anticipated or mitigated at all',
        'Written specifications are a waste of time because verbal agreements are always clear and sufficient',
        'Modular design makes systems harder to maintain because more components means more potential failures',
        'All decisions should be made by a single authority because group input always leads to poor outcomes',
        'Prototype evaluation serves no purpose because initial versions never reveal useful design insights',
        'Security measures are unnecessary for internal systems because all users are inherently trustworthy',
        'Version tracking provides no benefit because only the most recent output matters in any workflow',
        'Resource allocation should never be planned in advance because needs cannot be predicted at all',
        'Visual representations of data provide no insight beyond what raw numbers already communicate clearly',
        'Cross-functional collaboration introduces unnecessary complexity and should be completely avoided',
        'Structured methodologies slow down progress and should be replaced with unplanned ad hoc approaches',
        'Continuous monitoring of outcomes provides no actionable information for improving future performance',
        'Redundancy in systems is always wasteful and should be eliminated to reduce costs at every level',
        'User feedback has no value in improving products because designers always know best what users need',
        'Detailed analysis of failures provides no useful lessons because each situation is completely unique',
        'Deadlines have no effect on project outcomes because quality work cannot be scheduled or time-bound',
        'Standardized processes reduce creativity and should be abandoned in favor of individual improvisation',
        'Comprehensive training programs provide no measurable return on investment for any organization',
        'Delegation of responsibilities always leads to reduced accountability and worse overall outcomes',
        'Long-term planning is futile because external conditions always change in completely unpredictable ways',
        'Verification and validation steps are redundant because properly trained teams never make mistakes',
        'External benchmarking against industry standards provides no meaningful insight for improvement',
        'Process documentation should only be created after a project has completely failed beyond recovery',
        'Iterative refinement produces worse results than completing the entire work in a single pass',
    ],
}
def _fallback_question_from_sentence(sentence, q_type, marks, idx, sentence_pool=None, used_options=None, subject='generic'):
    # Only embed sentence in stem if it looks like real academic content
    _FB_JUNK = (
        'about me', 'youtube', 'project.eu', 'startup', 'hobby',
        'tourism', 'multinational', 'maqbool', 'mid semester',
        'final exam', 'assignment', 'teaching platform',
    )
    sentence_clean = sentence.strip()
    sl = sentence_clean.lower()
    # Extra junk patterns: colon-dash headings ("Working Project: -project"), bare labels, etc.
    _extra_junk = (
        bool(re.search(r':\s*-', sentence_clean)), # "Something: -subitem"
        bool(re.search(r'-\s*project\b', sl)), # trailing "-project"
        bool(re.match(r'^[\w\s]+:\s*\S', sentence_clean) and len(sentence_clean) < 50), # short "Label: value"
        len(sentence_clean.split()) <= 4, # bare heading (≤4 words)
    )
    safe = (not any(p in sl for p in _FB_JUNK)
            and not re.search(r'https?://', sl)
            and not any(_extra_junk))
    # Stricter quality gate for embedding sentence in Short/Long stems
    # (Short/Long stems quote the sentence directly so it must be clean AND on-topic)
    _embed_ok = (safe
                 and len(sentence_clean.split()) >= 8
                 and sentence_clean[0].isupper()
                 and 'and/or' not in sentence_clean
                 and not any(c in sentence_clean for c in _MCQ_BULLET_CHARS)
                 and not re.search(r'\w\s+-[a-z]', sentence_clean) # no space-hyphen
                 and sentence_clean.split()[-1].lower().rstrip('.,;:?!') not in _MCQ_DANGLE_WORDS # no trailing dangle
                 and _is_on_topic(sentence_clean, subject) # NEVER embed off-topic sentences
                 )
    generic_stem = 'Explain the key concept from the provided material, using examples where appropriate.'
    if q_type == 'MCQ':
        # ── Try to extract a concept for a specific stem ──
        concept, defn = _extract_concept_from_sentence(sentence_clean)
        # Validate concept: must pass format check AND be on-topic for the subject
        if (concept and defn and _valid_mcq_option(defn[:150])
                and _is_valid_topic(concept) and _is_on_topic(concept, subject)):
            # Concept-based stem (much better than generic truth stems)
            _CONCEPT_STEMS = [
                f'Which of the following best describes what {concept} means?',
                f'A student asks: "What is {concept}?" Which answer is most accurate?',
                f'Which statement correctly explains {concept}?',
                f'If asked to define {concept} on an exam, which response would earn full marks?',
                f'Which of the following is the most accurate description of {concept}?',
                f'An instructor asks you to explain {concept}. Which response is correct?',
            ]
            import random as _rng
            _rng.seed(idx + 77)
            stem = _CONCEPT_STEMS[idx % len(_CONCEPT_STEMS)]
            correct_opt = defn[:150].rstrip('.,;:')
            if not correct_opt[0].isupper():
                correct_opt = correct_opt[0].upper() + correct_opt[1:]
        else:
            _MCQ_TRUTH_STEMS = [
                'A student is reviewing for an exam. Which of the following statements should they consider correct?',
                'Which of the following accurately describes a key concept from the course material?',
                'During a revision session, which point would be correct to include in your notes?',
                'Which statement below would a subject-matter expert agree with?',
                'If you were explaining this topic to a classmate, which statement would be accurate?',
                'Which option correctly represents a principle covered in the course?',
                'When preparing summary notes, which of the following should be included as accurate?',
                'A peer asks you to verify a fact. Which of these statements is correct?',
                'Which of the following would receive full marks as a correct statement on an exam?',
                'Which choice best represents an accepted concept from the course content?',
                'From the study material, which of the following is a valid claim?',
                'Which of these statements aligns with the material discussed in the course?',
                'If you were writing flash-cards for revision, which statement belongs on the correct side?',
                'Which of the following ideas is consistent with what was taught in this course?',
            ]
            stem = _MCQ_TRUTH_STEMS[idx % len(_MCQ_TRUTH_STEMS)]
            # Quality filter: sentence must pass _valid_mcq_option
            _s_words = sentence_clean.split()
            _s_ok = (safe
                     and len(_s_words) >= 10
                     and _valid_mcq_option(sentence_clean[:150]))
            if _s_ok and (sentence_clean[:150].rstrip('.,;:').lower().strip() not in (used_options or set())):
                correct_opt = sentence_clean[:150].rstrip('.,;:')
            else:
                _FALLBACK_CORRECT = _CORRECT_POOLS.get(_pool_key(subject), _CORRECT_POOLS['generic'])
                # Pick a fallback correct answer not already used in the exam
                _fc_start = idx % len(_FALLBACK_CORRECT)
                _fc_chosen = None
                for _fc_i in range(len(_FALLBACK_CORRECT)):
                    _fc_cand = _FALLBACK_CORRECT[(_fc_start + _fc_i) % len(_FALLBACK_CORRECT)]
                    if _fc_cand.lower().strip() not in (used_options or set()):
                        _fc_chosen = _fc_cand
                        break
                if _fc_chosen:
                    correct_opt = _fc_chosen
                else:
                    # Pool exhausted — try other subject pools before duplicating
                    _alt_pools = [v for k, v in _CORRECT_POOLS.items() if k != subject and k != 'generic']
                    import random as _rng_alt
                    _rng_alt.seed(idx + 200)
                    _rng_alt.shuffle(_alt_pools)
                    _found_alt = False
                    for _alt_pool in _alt_pools:
                        for _alt_cand in _alt_pool:
                            if _alt_cand.lower().strip() not in (used_options or set()):
                                correct_opt = _alt_cand
                                _found_alt = True
                                break
                        if _found_alt:
                            break
                    if not _found_alt:
                        correct_opt = _FALLBACK_CORRECT[_fc_start]
        # ── Build distractors: prioritize STATIC pool, then validated source sentences ──
        import random as _rng
        _rng.seed(idx + 99)
        wrong_opts = []
        correct_lower = correct_opt.lower().strip()
        _used_lower = {correct_lower}
        # ── Static wrong pool (clean, guaranteed quality) — always try first ──
        _STATIC_WRONG = _WRONG_POOLS.get(_pool_key(subject), _WRONG_POOLS['generic'])
        static_copy = list(_STATIC_WRONG)
        _rng.shuffle(static_copy)
        for s in static_copy:
            sl = s.lower().strip()
            if sl in _used_lower:
                continue
            # Skip options already used in previous questions this exam
            if sl in (used_options or set()):
                continue
            wrong_opts.append(s)
            _used_lower.add(sl)
            if len(wrong_opts) >= 3:
                break
        # ── If still need more, try validated source text sentences ──
        if len(wrong_opts) < 3 and sentence_pool:
            pool_copy = list(sentence_pool)
            _rng.shuffle(pool_copy)
            for s in pool_copy:
                s = s.strip()
                if not _valid_mcq_option(s):
                    continue
                # Reject source-text sentences that belong to a different subject
                if not _is_on_topic(s, subject):
                    continue
                sl = s.lower().strip()
                if sl in _used_lower:
                    continue
                if sl in (used_options or set()):
                    continue
                if sl == sentence_clean.lower().strip():
                    continue
                # Check word-level similarity with correct and existing distractors
                s_words = set(sl.split())
                too_similar = False
                for existing in [correct_lower] + [w.lower() for w in wrong_opts]:
                    e_words = set(existing.split())
                    overlap = len(s_words & e_words) / max(1, len(s_words | e_words))
                    if overlap > 0.55:
                        too_similar = True
                        break
                if too_similar:
                    continue
                # Capitalize first letter
                opt = s[:150].rstrip('.,;:')
                if opt and not opt[0].isupper():
                    opt = opt[0].upper() + opt[1:]
                wrong_opts.append(opt)
                _used_lower.add(sl)
                if len(wrong_opts) >= 3:
                    break
        # Shuffle correct answer position
        all_opts = [correct_opt] + wrong_opts[:3]
        while len(all_opts) < 4:
            all_opts.append('No additional information is available for this particular option')
        _rng.seed(idx + 42)
        correct_idx = _rng.randint(0, 3)
        all_opts[0], all_opts[correct_idx] = all_opts[correct_idx], all_opts[0]
        correct_letter = chr(65 + correct_idx) # A/B/C/D
        return {
            'question_text': stem,
            'question_type': 'MCQ',
            'difficulty': 'medium',
            'marks': marks,
            'options': {
                'A': all_opts[0],
                'B': all_opts[1],
                'C': all_opts[2],
                'D': all_opts[3]
            },
            'correct_answer': correct_letter,
            'explanation': None,
            'model_answer': None
        }
    if q_type == 'Short Answer':
        if _embed_ok and len(sentence_clean.split()) >= 8:
            _SHORT_STEMS = [
                f'Read the following statement: \u201c{sentence_clean[:120]}\u201d. In your own words, explain the concept it describes and provide one practical example.',
                f'A classmate does not understand: \u201c{sentence_clean[:120]}\u201d. Explain it clearly in 2\u20133 sentences so they can grasp the key idea.',
                f'Consider this idea: \u201c{sentence_clean[:120]}\u201d. Why is it important in practice? Explain briefly with a real-world context.',
                f'Interpret the following: \u201c{sentence_clean[:120]}\u201d. What does it mean and what implications does it have? Give a brief example.',
            ]
            stem = _SHORT_STEMS[idx % len(_SHORT_STEMS)]
        else:
            # Extract a VALIDATED topic — never embed raw PDF garbage
            _fb_topic = _pick_valid_topic(sentence_clean, idx, subject)
            _SHORT_TOPIC_STEMS = [
                f'What is {_fb_topic}? Provide a clear definition and one practical example.',
                f'Explain why {_fb_topic} is considered important. What would happen without it?',
                f'Describe the role {_fb_topic} plays in a typical workflow. Give an example.',
                f'How does {_fb_topic} differ from alternative approaches? State at least one advantage.',
            ]
            stem = _SHORT_TOPIC_STEMS[idx % len(_SHORT_TOPIC_STEMS)]
        return {
            'question_text': stem,
            'question_type': 'Short Answer',
            'difficulty': 'medium',
            'marks': marks,
            'options': None,
            'correct_answer': None,
            'explanation': None,
            'model_answer': sentence_clean[:220] if safe else generic_stem
        }
    # Always obtain a VALIDATED topic for Long Answer
    _la_topic = _pick_valid_topic(sentence_clean, idx, subject)
    if _embed_ok:
        _LONG_FALLBACK_STEMS = [
            f'Consider the statement: "{sentence_clean[:120]}". Write a detailed explanation covering what it means, why it is significant, any challenges it presents, and support your answer with a real-world example.',
            f'Suppose you are writing a textbook section that begins with: "{sentence_clean[:120]}". Explain the concept thoroughly, discuss its benefits and limitations, and describe a practical application.',
            f'A professional asks you to elaborate on: "{sentence_clean[:120]}". Provide a comprehensive answer covering the meaning, practical implications, potential challenges, and a scenario demonstrating its use.',
        ]
    else:
        _LONG_FALLBACK_STEMS = [
            f'Explain {_la_topic} in detail. Include its definition, purpose, how it works, and provide a real-world example of its application.',
            f'A professional needs to understand {_la_topic}. Provide a thorough explanation including its purpose, mechanism, advantages, and one practical example.',
            f'Compare {_la_topic} with an alternative approach. Discuss the trade-offs involved and recommend when each should be used, with justification.',
        ]
    return {
        'question_text': _LONG_FALLBACK_STEMS[idx % len(_LONG_FALLBACK_STEMS)],
        'question_type': 'Long Answer',
        'difficulty': 'hard',
        'marks': marks,
        'options': None,
        'correct_answer': None,
        'explanation': None,
        'model_answer': sentence[:300]
    }
def _coerce_question_shape(q, q_type, marks, subject='generic'):
    base_text = (q.get('question_text') or q.get('question') or '').strip() or 'Explain the concept from the material.'
    difficulty = (q.get('difficulty') or 'medium').lower()
    if difficulty not in ('easy', 'medium', 'hard'):
        difficulty = 'medium'
    # If stem contains off-topic content, rebuild it using subject topic bank
    if not _is_on_topic(base_text, subject):
        bank = _APP_SUBJECT_TOPIC_BANKS.get(subject, _APP_SUBJECT_TOPIC_BANKS['generic'])
        _bt_idx = hash(base_text) % len(bank)
        _bt_topic = bank[_bt_idx]
        if q_type == 'MCQ':
            _MCQ_REGEN = [
                f'Which of the following correctly describes {_bt_topic}?',
                f'Which statement best explains {_bt_topic}?',
                f'What does {_bt_topic} primarily involve?',
            ]
            base_text = _MCQ_REGEN[_bt_idx % len(_MCQ_REGEN)]
        elif q_type == 'Short Answer':
            base_text = f'Briefly explain {_bt_topic} in 2-3 lines.'
        else:
            base_text = f'Discuss {_bt_topic} in detail with one practical example.'
    question = {
        'question_text': base_text,
        'question_type': q_type,
        'difficulty': difficulty,
        'marks': marks if marks and marks > 0 else int(q.get('marks') or 1),
        'options': q.get('options'),
        'correct_answer': q.get('correct_answer'),
        'explanation': q.get('explanation'),
        'model_answer': q.get('model_answer') or q.get('reference_answer')
    }
    if q_type == 'MCQ':
        if not isinstance(question['options'], dict) or len(question['options']) < 2:
            question['options'] = _to_mcq_options(base_text)
        else:
            # Filter out off-topic options and replace with static pool entries
            _det_subj = subject
            _opts = question['options']
            _correct_key = str(question.get('correct_answer') or 'A').strip().upper()[:1]
            _needs_replace = []
            for _ok, _ov in _opts.items():
                if _ok == _correct_key:
                    continue # keep correct answer as-is
                if isinstance(_ov, str) and not _is_on_topic(_ov, _det_subj):
                    _needs_replace.append(_ok)
            if _needs_replace:
                import random as _rng_cq
                _rng_cq.seed(hash(base_text) + 99)
                _wrong_pool = _WRONG_POOLS.get(_pool_key(_det_subj), _WRONG_POOLS['generic'])
                _pool_copy = list(_wrong_pool)
                _rng_cq.shuffle(_pool_copy)
                _existing_vals = {str(v).lower().strip() for v in _opts.values()}
                _pi = 0
                for _rk in _needs_replace:
                    while _pi < len(_pool_copy):
                        _cand = _pool_copy[_pi]
                        _pi += 1
                        if _cand.lower().strip() not in _existing_vals:
                            _opts[_rk] = _cand
                            _existing_vals.add(_cand.lower().strip())
                            break
                question['options'] = _opts
        if not question['correct_answer']:
            question['correct_answer'] = 'A'
        question['model_answer'] = None
    else:
        question['options'] = None
        question['correct_answer'] = None
        if not question['model_answer']:
            question['model_answer'] = base_text[:260]
    return question
def enforce_distribution(questions, source_text, mcq_count, short_count, long_count, mcq_marks, short_marks, long_marks, subject=None):
    requested_total = mcq_count + short_count + long_count
    if requested_total <= 0:
        return questions
    normalized = []
    for q in (questions or []):
        if isinstance(q, dict):
            normalized.append(q)
    pools = {
        'MCQ': [],
        'Short Answer': [],
        'Long Answer': [],
        'OTHER': []
    }
    for q in normalized:
        q_type = normalize_question_type(q.get('question_type'))
        if q_type in pools:
            pools[q_type].append(q)
        else:
            pools['OTHER'].append(q)
    fallback_sentences = _split_sentences_for_fallback(source_text)
    fallback_cursor = 0
    # Use caller-provided subject; only auto-detect as last resort.
    if subject:
        # Convert QG key (e.g. 'database_fundamentals') to pool key ('database')
        _detected_subject = _pool_key(subject)
    else:
        _detected_subject = _detect_subject(source_text)
    def next_fallback_sentence():
        nonlocal fallback_cursor
        sentence = fallback_sentences[fallback_cursor % len(fallback_sentences)]
        fallback_cursor += 1
        return sentence
    def take_or_build(target_type, count, marks):
        items = []
        _used_opts = set() # track used option texts across questions for dedup
        for _ in range(count):
            src = None
            if pools[target_type]:
                src = pools[target_type].pop(0)
            elif pools['OTHER']:
                src = pools['OTHER'].pop(0)
            else:
                # For MCQ: skip stealing from Short/Long pools (it ruins both)
                # Instead, go straight to fallback MCQ generation from source text.
                if target_type != 'MCQ':
                    for alt in ('MCQ', 'Short Answer', 'Long Answer'):
                        if pools[alt]:
                            src = pools[alt].pop(0)
                            break
            if src is None:
                built = _fallback_question_from_sentence(next_fallback_sentence(), target_type, marks, len(items), sentence_pool=fallback_sentences, used_options=_used_opts, subject=_detected_subject)
            elif target_type == 'MCQ' and normalize_question_type(src.get('question_type')) != 'MCQ':
                # Don't coerce Short/Long into MCQ — build a fresh fallback MCQ from source text
                # and put the Short/Long question back into its pool so it's available later.
                orig_type = normalize_question_type(src.get('question_type'))
                if orig_type in pools:
                    pools[orig_type].insert(0, src)
                built = _fallback_question_from_sentence(next_fallback_sentence(), 'MCQ', marks, len(items), sentence_pool=fallback_sentences, used_options=_used_opts, subject=_detected_subject)
            else:
                built = _coerce_question_shape(src, target_type, marks, subject=_detected_subject)
            # Record all option texts to prevent duplicates across questions
            if target_type == 'MCQ' and isinstance(built.get('options'), dict):
                for v in built['options'].values():
                    if v and isinstance(v, str):
                        _used_opts.add(v.lower().strip())
            items.append(built)
        return items
    final_questions = []
    final_questions.extend(take_or_build('MCQ', mcq_count, mcq_marks))
    final_questions.extend(take_or_build('Short Answer', short_count, short_marks))
    final_questions.extend(take_or_build('Long Answer', long_count, long_marks))
    # Reassign sequential question_order after grouping
    for idx, q in enumerate(final_questions):
        q['question_order'] = idx + 1
    return final_questions[:requested_total]
@app.route('/test', methods=['GET'])
def simple_test():
    return "Backend is working!", 200
# ==========================================
# ROUTE 1: Health Check
# ==========================================
@app.route('/api/health', methods=['GET'])
def health_check():
    """Check if server is running"""
    model_status = get_generation_model_status()
    question_generation_mode = (
        "Qwen LoRA"
        if model_status.get("use_qwen_lora")
        else "CodeBERT + Ollama Qwen 2.5 7B"
    )
    return jsonify({
        'status': 'OK',
        'message': 'AI Backend Server is running',
        'models': {
            'question_generation': question_generation_mode,
            'essay_grading': 'Sentence-BERT',
            'topic_extraction': 'BERTopic'
        },
        'model_runtime': model_status,
        'version': '1.0.0'
    }), 200
# ==========================================
# ROUTE 2: Upload File & Generate Questions
# ==========================================
@app.route('/api/generate-questions', methods=['OPTIONS'])
def generate_questions_options():
    """Handle preflight CORS request for generate-questions"""
    # Let flask_cors inject the CORS headers to avoid duplicates.
    return ('', 204)
@app.route('/api/generate-questions', methods=['POST'])
def generate_questions():
    """
    Upload PDF/DOCX → Extract text → Generate questions with AI
   
    Request:
        - file: PDF/DOCX file
        - exam_id: (optional) Exam ID to save questions
        - subject: Subject name (data_structures, algorithms, etc.)
        - num_questions: Number of questions to generate (default: 10)
        - difficulty: easy/medium/hard (optional)
   
    Response:
        {
            "success": true,
            "message": "Generated X questions",
            "questions": [...],
            "topics": [...]
        }
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        logger.info("Question generation request started")
       
        # Validate file upload (single or multiple)
        uploaded_files = request.files.getlist('files')
        if not uploaded_files:
            single_file = request.files.get('file')
            if single_file:
                uploaded_files = [single_file]
        if not uploaded_files:
            return jsonify({'error': 'No file uploaded'}), 400
        uploaded_files = [f for f in uploaded_files if f and f.filename]
        if not uploaded_files:
            return jsonify({'error': 'No file selected'}), 400
        invalid_names = [f.filename for f in uploaded_files if not allowed_file(f.filename)]
        if invalid_names:
            return jsonify({
                'error': 'Invalid file type. Allowed: PDF, DOC, DOCX, PPT, PPTX',
                'invalid_files': invalid_names
            }), 400
       
        # Get parameters
        exam_id = request.form.get('exam_id')
        subject_label_raw = request.form.get('subject', 'general')
        subject = subject_label_raw
        num_questions = int(request.form.get('num_questions', 10))
        mcq_count = int(request.form.get('mcq_count', 0))
        short_count = int(request.form.get('short_count', 0))
        long_count = int(request.form.get('long_count', 0))
        mcq_marks = int(request.form.get('mcq_marks', 1) or 1)
        short_marks = int(request.form.get('short_marks', 3) or 3)
        long_marks = int(request.form.get('long_marks', 5) or 5)
        teacher_id = _user_ctx_profile_id(user_ctx)
        course_id = request.form.get('course_id')
       
        requested_total = mcq_count + short_count + long_count
        if requested_total > 0:
            num_questions = requested_total
        use_ollama_flag = str(request.form.get('use_ollama', '')).strip().lower() in ("1", "true", "yes", "on")
        # Read difficulty — enforce it on ALL generated questions
        requested_difficulty = str(request.form.get('difficulty', '') or '').strip().lower()
        if requested_difficulty not in ('easy', 'medium', 'hard'):
            requested_difficulty = ''  # empty = let generator decide
        logger.info("QG params: subject=%s, num_questions=%d, difficulty=%s, use_ollama=%s",
                    subject, num_questions, requested_difficulty or 'auto', use_ollama_flag)
       
        # Normalize and validate subject
        subject_raw = str(subject or 'general').strip().lower()
        user_selected_specific = subject_raw not in ('general', 'auto', 'generic', '')
        # Collapse any symbols/parentheses to underscores so "Database Management (SQL)" is recognized.
        subject = re.sub(r'[^a-z0-9]+', '_', subject_raw).strip('_')
        if 'database' in subject or 'dbms' in subject or 'sql' in subject:
            subject = 'database_fundamentals'
            user_selected_specific = True
        subject_aliases = {
            'python': 'python_programming',
            'python_programming_basics': 'python_programming',
            'database_fundamentals': 'database_fundamentals',
            'database_management': 'database_fundamentals',
            'database_systems': 'database_fundamentals',
            'database_management_sql': 'database_fundamentals',
            'database_management_systems': 'database_fundamentals',
            'web_development_basics': 'web_development',
            'software_engineering_fundamentals': 'software_engineering',
            'object_oriented_programming_basics': 'object_oriented_programming',
            'oop': 'object_oriented_programming',
            'oop_basics': 'object_oriented_programming'
        }
        subject = subject_aliases.get(subject, subject)
        valid_subjects = [
            'data_structures',
            'algorithms',
            'database_fundamentals',
            'database_systems',
            'operating_systems',
            'software_engineering',
            'python_programming',
            'web_development',
            'object_oriented_programming',
            'machine_learning',
            'general'
        ]
       
        if subject not in valid_subjects:
            subject = 'general'
       
        # Save and extract from uploaded files
        saved_files = []
        extracted_chunks = []
        failed_extractions = []
        # ── Auto-correct subject from actual text content ────────────
        # The frontend dropdown may not match the uploaded PDF. Use
        # _detect_subject() (DistilBERT → keyword fallback) on the text
        # AFTER extraction to override when there is a clear mismatch.
        _POOL_TO_QG_SUBJECT = {
            'database': 'database_fundamentals',
            'python': 'python_programming',
            'oop': 'object_oriented_programming',
            'web': 'web_development',
            'se': 'software_engineering',
            'generic': 'general',
        }
        _QG_TO_POOL = {v: k for k, v in _POOL_TO_QG_SUBJECT.items()}
        _override_subject_later = True  # flag — do after text extraction
        logger.info("QG Step 1: Extracting text from %d file(s)...", len(uploaded_files))
        for idx, current_file in enumerate(uploaded_files, start=1):
            filename = secure_filename(current_file.filename)
            timestamp = f"{int(time.time() * 1000)}_{idx}"
            unique_filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            current_file.save(filepath)
            file_size = os.path.getsize(filepath)
            logger.debug("File saved: %s (%d bytes)", unique_filename, file_size)
            try:
                chunk = extract_text_from_file(filepath) or ""
            except Exception:
                chunk = ""
            if chunk and len(chunk.strip()) >= 100:
                extracted_chunks.append(chunk.strip())
                saved_files.append({
                    'filename': filename,
                    'stored_name': unique_filename,
                    'path': filepath,
                    'content_type': current_file.content_type,
                    'size': file_size,
                    'text_length': len(chunk)
                })
            else:
                failed_extractions.append(filename)
        if not extracted_chunks:
            return jsonify({
                'error': 'Failed to extract sufficient text from uploaded files. Files may be empty or corrupted.',
                'failed_files': failed_extractions
            }), 500
        extracted_text = "\n\n".join(extracted_chunks)
        logger.info("QG: Extracted %d chars from %d file(s)", len(extracted_text), len(saved_files))
        # Length & quality check after cleaning
        if len(extracted_text.strip()) < 300:
            return jsonify({
                'error': 'Extracted material is too short or empty after cleaning. Please upload clearer Database slides/notes.',
                'length': len(extracted_text)
            }), 400
        max_chars = int(os.getenv("QG_MAX_CHARS", "18000"))
        if max_chars > 0 and len(extracted_text) > max_chars:
            logger.debug("QG: Truncating text from %d to %d chars", len(extracted_text), max_chars)
            extracted_text = extracted_text[:max_chars]
        # ── Auto-correct subject from actual content ─────────────────────
        # Only override if the user chose a generic/auto subject (not a
        # specific one) AND there is enough extracted text for reliable detection.
        _user_chose_specific = bool(user_selected_specific)
        if _override_subject_later and not _user_chose_specific and len(extracted_text) >= 500:
            detected_pool = _detect_subject(extracted_text)
            detected_qg = _POOL_TO_QG_SUBJECT.get(detected_pool, 'general')
            frontend_pool = _QG_TO_POOL.get(subject, 'generic')
            if detected_pool != 'generic' and detected_pool != frontend_pool:
                logger.info("QG: Subject override frontend='%s' → detected='%s'", subject, detected_qg)
                subject = detected_qg
        # Step 2: Extract topics (optional, disabled by default for speed)
        topics = []
        enable_topic_extraction = str(os.getenv("ENABLE_TOPIC_EXTRACTION", "false")).strip().lower() in ("1", "true", "yes", "on")
        if enable_topic_extraction:
            try:
                topics = extract_topics_from_text(extracted_text, num_topics=5)
                logger.debug("QG: Found %d topics", len(topics))
            except Exception as topic_exc:
                logger.warning("QG: Topic extraction failed: %s", topic_exc)
                topics = []
       
        # Step 3: Generate questions using AI
        logger.info("QG Step 3: Generating %d questions for subject=%s", num_questions, subject)
        old_ollama = os.getenv("OLLAMA_MAX_CALLS_CPU")
        if use_ollama_flag:
            os.environ["OLLAMA_MAX_CALLS_CPU"] = "1"
        try:
            questions = generate_questions_from_text(
                text=extracted_text,
                subject=subject,
                num_questions=num_questions
            )
        finally:
            if use_ollama_flag:
                if old_ollama is None:
                    os.environ.pop("OLLAMA_MAX_CALLS_CPU", None)
                else:
                    os.environ["OLLAMA_MAX_CALLS_CPU"] = old_ollama
        
        if not questions:
            return jsonify({'error': 'Failed to generate questions. Please try again.'}), 500
        
        # ── QUALITY IMPROVEMENTS: Apply grounding, duplicate detection, validation ────
        logger.info("QG: Applying quality improvements (grounding, duplicate detection, validation)...")
        try:
            from models.question_generator import apply_quality_improvements
            questions, quality_report = apply_quality_improvements(
                questions=questions,
                original_text=extracted_text,
                subject=subject
            )
            logger.info("QG: Quality improvements completed. Report: %s", quality_report.get('grounding'))
        except ImportError:
            logger.warning("QG: Quality improvements module not available, skipping")
            quality_report = {'grounding': None, 'duplicates': None, 'validation': None}
        except Exception as e:
            logger.warning("QG: Quality improvements failed (non-blocking): %s", e)
            quality_report = {'grounding': None, 'duplicates': None, 'validation': None}

        logger.info("QG: Generated %d questions for subject=%s", len(questions), subject)

        # Enforce requested difficulty on ALL questions
        if requested_difficulty:
            for q in questions:
                q['difficulty'] = requested_difficulty
            logger.debug("QG: Difficulty locked to '%s' on all %d questions", requested_difficulty, len(questions))
        # Apply strict requested distribution and fill missing questions if needed.
        if requested_total > 0:
            questions = enforce_distribution(
                questions=questions,
                source_text=extracted_text,
                mcq_count=mcq_count,
                short_count=short_count,
                long_count=long_count,
                mcq_marks=mcq_marks,
                short_marks=short_marks,
                long_marks=long_marks,
                subject=subject
            )
            logger.debug("QG: Distribution enforced => total=%d, mcq=%d, short=%d, long=%d",
                         len(questions), mcq_count, short_count, long_count)
       
        # Step 4: Save to database if exam_id provided
        supabase = get_supabase()
        saved_questions = []
        save_errors = []
       
        if exam_id:
            exam_row = None
            try:
                exam_lookup = db_exec(lambda: supabase.table('exams').select('exam_id,id').eq('exam_id', exam_id).limit(1).execute())
                if exam_lookup.data:
                    exam_row = exam_lookup.data[0]
                else:
                    exam_lookup = db_exec(lambda: supabase.table('exams').select('exam_id,id').eq('id', exam_id).limit(1).execute())
                    if exam_lookup.data:
                        exam_row = exam_lookup.data[0]
            except Exception as exam_lookup_err:
                logger.error("QG: Could not verify exam %s: %s", exam_id, exam_lookup_err)
                return jsonify({
                    'success': False,
                    'error': 'Could not verify the exam before saving generated questions.',
                    'details': str(exam_lookup_err)
                }), 500

            if not exam_row:
                return jsonify({
                    'success': False,
                    'error': 'Exam record was not found in the database. Please recreate the exam and generate questions again.',
                    'exam_id': exam_id
                }), 409

            _, owner_error = _require_teacher_exam_owner(supabase, exam_id, user_ctx)
            if owner_error:
                return owner_error

            exam_id = exam_row.get('exam_id') or exam_row.get('id') or exam_id
            logger.info("QG Step 4: Saving questions to exam %s", exam_id)
            # Regeneration flow: remove older draft questions first.
            try:
                db_exec(lambda: supabase.table('questions').delete().eq('exam_id', exam_id).execute())
            except Exception as clear_err:
                logger.warning("QG: Could not clear existing questions for exam %s: %s", exam_id, clear_err)
            saved_orders = set()
            for i, q in enumerate(questions):
                try:
                    q_text = (q.get('question_text') or q.get('question') or '').strip()
                    if not q_text:
                        q_text = f"Generated question {i + 1}"
                    q_marks = int(q.get('marks') or 1)
                    if q_marks <= 0:
                        q_marks = 1
                    question_data = {
                        'exam_id': exam_id,
                        'question_text': _sanitize_text(q_text),
                        'question_type': to_db_question_type(q.get('question_type')),
                        'difficulty': q.get('difficulty', 'medium'),
                        'marks': q_marks,
                        'options': _sanitize_jsonish(q.get('options')),
                        'correct_answer': _sanitize_text(q.get('correct_answer')),
                        'explanation': _sanitize_text(q.get('explanation')),
                        'ai_generated': True,
                        'topic': _sanitize_text(q.get('topic', subject)),
                        'question_order': i + 1
                    }
                    inserted = False
                    last_err = None
                    for qt in build_question_type_candidates(q.get('question_type')):
                        try:
                            question_data['question_type'] = qt
                            if not is_objective_type(qt):
                                question_data['options'] = None
                                question_data['correct_answer'] = None
                            else:
                                if not isinstance(question_data.get('options'), dict) or len(question_data['options']) < 2:
                                    question_data['options'] = {'A': 'True', 'B': 'False'}
                                if not question_data.get('correct_answer'):
                                    question_data['correct_answer'] = 'A'
                            result = db_exec(lambda: supabase.table('questions').insert(question_data).execute())
                            if result.data:
                                saved_questions.append(result.data[0])
                                saved_orders.add(i + 1)
                                inserted = True
                                break
                        except Exception as ie:
                            last_err = ie
                            continue
                    if not inserted and last_err:
                        raise last_err
                except Exception as e:
                    err_text = str(e)
                    logger.error("QG: Error saving question %d: %s", i + 1, err_text)
                    save_errors.append(f"q{i+1} save: {err_text}")
            # Best-effort top-up to avoid partial-save failure.
            if requested_total > 0 and len(saved_questions) < requested_total:
                logger.warning("QG: Top-up started: saved=%d requested=%d", len(saved_questions), requested_total)
                for i, original_q in enumerate(questions):
                    order = i + 1
                    if order in saved_orders:
                        continue
                    try:
                        target_type = normalize_question_type(original_q.get('question_type'))
                        fallback_q = _coerce_question_shape(
                            original_q,
                            target_type,
                            int(original_q.get('marks') or 1),
                            subject=subject or 'generic'
                        )
                        db_type = to_db_question_type(fallback_q.get('question_type'))
                        fallback_data = {
                            'exam_id': exam_id,
                            'question_text': _sanitize_text((fallback_q.get('question_text') or f"Generated question {order}").strip()),
                            'question_type': db_type,
                            'difficulty': fallback_q.get('difficulty', 'medium'),
                            'marks': int(fallback_q.get('marks') or 1),
                            'options': _sanitize_jsonish(fallback_q.get('options')),
                            'correct_answer': _sanitize_text(fallback_q.get('correct_answer')),
                            'explanation': _sanitize_text(fallback_q.get('explanation')),
                            'ai_generated': True,
                            'topic': _sanitize_text(fallback_q.get('topic', subject)),
                            'question_order': order
                        }
                        if not is_objective_type(db_type):
                            fallback_data['options'] = None
                            fallback_data['correct_answer'] = None
                        else:
                            if not isinstance(fallback_data.get('options'), dict) or len(fallback_data['options']) < 2:
                                fallback_data['options'] = {'A': 'True', 'B': 'False'}
                            if not fallback_data.get('correct_answer'):
                                fallback_data['correct_answer'] = 'A'
                        result = db_exec(lambda: supabase.table('questions').insert(fallback_data).execute())
                        if result.data:
                            saved_questions.append(result.data[0])
                            saved_orders.add(order)
                    except Exception as topup_err:
                        err_text = str(topup_err)
                        logger.error("QG: Top-up failed for question %d: %s", order, err_text)
                        save_errors.append(f"q{order} topup: {err_text}")
            # Also save uploaded file metadata
            if teacher_id and course_id:
                try:
                    for meta in saved_files:
                        file_data = {
                            'teacher_id': teacher_id,
                            'course_id': course_id,
                            'filename': meta['filename'],
                            'file_path': meta['path'],
                            'file_type': meta['content_type'],
                            'file_size': meta['size'],
                            'processed': True,
                            'extracted_text': extracted_text[:5000],
                            'topics_extracted': topics
                        }
                        supabase.table('uploaded_files').insert(file_data).execute()
                    logger.debug("QG: File metadata saved (%d file(s))", len(saved_files))
                except Exception as e:
                    logger.warning("QG: Error saving file metadata: %s", e)

            logger.info("QG: Generated and saved %d questions for exam %s", len(saved_questions), exam_id)

            # Send minimal response - questions are already saved in database
            if requested_total > 0 and len(saved_questions) < requested_total:
                logger.error("QG: Saved fewer questions than requested: saved=%d requested=%d",
                             len(saved_questions), requested_total)
                return jsonify({
                    'success': False,
                    'error': f'Only saved {len(saved_questions)} out of {requested_total} questions. Please try again.',
                    'diagnostics': save_errors[:8]
                }), 500
            response_questions = _sanitize_question_payload(questions)
            response_data = {
                'success': True,
                'message': f'Generated {len(questions)} questions and saved {len(saved_questions)}',
                'exam_id': exam_id,
                'questions_count': len(questions),
                'questions_saved_count': len(saved_questions),
                # Return generated payload (original intended types) for editor/preview UX.
                'questions': response_questions,
                'file_info': {
                    'files': [
                        {'filename': m['filename'], 'size': m['size'], 'text_length': m['text_length']}
                        for m in saved_files
                    ],
                    'failed_files': failed_extractions
                },
                'uploaded_files_count': len(saved_files),
                'quality_report': quality_report  # Include grounding, duplicate detection, validation results
            }
            return jsonify(response_data), 200

        else:
            logger.info("QG: Generated %d questions (not saved)", len(questions))
            # Return questions without saving
            return jsonify({
                'success': True,
                'message': f'Generated {len(questions)} questions',
                'questions': _sanitize_question_payload(questions),
                'topics': topics,
                'file_info': {
                    'files': [
                        {'filename': m['filename'], 'size': m['size'], 'text_length': m['text_length']}
                        for m in saved_files
                    ],
                    'failed_files': failed_extractions,
                    'text_length': len(extracted_text)
                },
                'uploaded_files_count': len(saved_files),
                'quality_report': quality_report  # Include grounding, duplicate detection, validation results
            }), 200

    except Exception as e:
        logger.error("ERROR in generate_questions: %s", e, exc_info=True)
        return jsonify({'error': str(e)}), 500
# ==========================================
# ROUTE 3: Grade Essay with AI
# ==========================================
@app.route('/api/grade-essay', methods=['POST'])
def grade_essay_endpoint():
    """
    Grade a student's essay answer using AI
   
    Request JSON:
        {
            "question_text": "Explain binary search",
            "reference_answer": "Binary search is...",
            "student_answer": "Binary search works by...",
            "max_marks": 10,
            "answer_id": "uuid" (optional)
        }
   
    Response:
        {
            "success": true,
            "grading": {
                "score": 7.5,
                "max_score": 10,
                "percentage": 75,
                "feedback": "...",
                "strengths": [...],
                "improvements": [...]
            }
        }
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        data = request.json
       
        # Validate required fields
        question_text = data.get('question_text')
        reference_answer = data.get('reference_answer')
        student_answer = data.get('student_answer')
        max_marks = data.get('max_marks', 10)
        answer_id = data.get('answer_id')
        attempt_id = data.get('attempt_id')
        requester_teacher_id = _user_ctx_profile_id(user_ctx)
       
        if not question_text:
            return jsonify({'error': 'question_text is required'}), 400
       
        if not reference_answer:
            return jsonify({'error': 'reference_answer is required'}), 400
       
        if not student_answer:
            return jsonify({'error': 'student_answer is required'}), 400
        check_attempt_id = attempt_id
        if not check_attempt_id and answer_id:
            try:
                ans_resp = get_supabase().table('student_answers').select('attempt_id').eq('answer_id', answer_id).limit(1).execute()
                if ans_resp.data and len(ans_resp.data) > 0:
                    check_attempt_id = ans_resp.data[0].get('attempt_id')
            except Exception:
                check_attempt_id = None
        if check_attempt_id:
            owner_supabase = get_supabase()
            attempt_row = _load_attempt_row(owner_supabase, check_attempt_id, 'attempt_id,exam_id')
            if not attempt_row:
                return jsonify({'error': 'Attempt not found'}), 404
            _, exam_auth_error = _require_teacher_exam_owner(owner_supabase, attempt_row.get('exam_id'), user_ctx)
            if exam_auth_error:
                return exam_auth_error
       
        logger.debug("Grading essay for question: %s...", question_text[:50])
        # Grade the essay using AI
        grading_result = _grade_essay_flex(
            question_text=question_text,
            reference_answer=reference_answer,
            student_answer=student_answer,
            max_marks=max_marks
        )
        if not grading_result:
            return jsonify({'error': 'Failed to grade essay'}), 500
        normalized = _normalize_grading_result(grading_result, max_marks=max_marks)
        logger.debug("Essay graded: %s/%s status=%s conf=%.2f",
                     normalized['score'], normalized['max_score'],
                     normalized['review_status'], normalized['confidence'])
        # Save to database if answer_id provided
        if answer_id:
            try:
                supabase = get_supabase()
                update_data = {
                    'marks_obtained': normalized['score'],
                    'max_marks': normalized['max_score'],
                    'ai_score': normalized['score'],
                    'similarity_with_model': normalized['confidence'],
                    'review_status': normalized['review_status'],
                    'is_manually_graded': False,
                    'ai_feedback': normalized['feedback']
                }
                if normalized['review_status'] == 'pending':
                    update_data['is_correct'] = None
                else:
                    update_data['is_correct'] = bool(normalized['score'] > 0)
                result = _update_answer_with_fallback(supabase, answer_id, update_data)
                if result.data:
                    return jsonify({
                        'success': True,
                        'message': 'Essay graded and saved successfully',
                        'grading': normalized
                    }), 200
                else:
                    logger.warning("No answer found with id: %s", answer_id)
            except Exception as e:
                logger.error("Error saving grade: %s", e)
                # Still return grading result even if save fails
        # Return grading without saving
        return jsonify({
            'success': True,
            'message': 'Essay graded successfully',
            'grading': normalized
        }), 200
       
    except Exception as e:
        logger.error("Error in grade_essay_endpoint: %s", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
# ==========================================
# ROUTE 4: Batch Grade Multiple Essays
# ==========================================
@app.route('/api/grade-batch', methods=['POST'])
def grade_batch():
    """
    Grade multiple essays at once (for entire exam)
   
    Request JSON:
        {
            "attempt_id": "uuid",
            "answers": [
                {
                    "answer_id": "uuid",
                    "question_text": "...",
                    "reference_answer": "...",
                    "student_answer": "...",
                    "max_marks": 10
                }
            ]
        }
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        data = request.json
        answers = data.get('answers', [])
        attempt_id = data.get('attempt_id')
        requester_teacher_id = _user_ctx_profile_id(user_ctx)
       
        if not answers:
            return jsonify({'error': 'No answers provided'}), 400
        if attempt_id:
            owner_supabase = get_supabase()
            attempt_row = _load_attempt_row(owner_supabase, attempt_id, 'attempt_id,exam_id')
            if not attempt_row:
                return jsonify({'error': 'Attempt not found'}), 404
            _, exam_auth_error = _require_teacher_exam_owner(owner_supabase, attempt_row.get('exam_id'), user_ctx)
            if exam_auth_error:
                return exam_auth_error
       
        logger.debug("Batch grading %d answers...", len(answers))
       
        graded_answers = []
        total_marks = 0
        total_max = 0
       
        supabase = get_supabase()
        for ans in answers:
            try:
                answer_max_marks = ans.get('max_marks', 10)
                # Grade the answer
                grading_raw = _grade_essay_flex(
                    question_text=ans.get('question_text', ''),
                    reference_answer=ans.get('reference_answer', ''),
                    student_answer=ans.get('student_answer', ''),
                    max_marks=answer_max_marks
                )
                if not grading_raw:
                    raise Exception('Failed to grade answer')
                grading = _normalize_grading_result(grading_raw, max_marks=answer_max_marks)
                # Save to database
                if ans.get('answer_id'):
                    update_data = {
                        'marks_obtained': grading['score'],
                        'max_marks': grading['max_score'],
                        'ai_score': grading['score'],
                        'similarity_with_model': grading['confidence'],
                        'review_status': grading['review_status'],
                        'is_manually_graded': False,
                        'ai_feedback': grading['feedback']
                    }
                    if grading['review_status'] == 'pending':
                        update_data['is_correct'] = None
                    else:
                        update_data['is_correct'] = bool(grading['score'] > 0)
                    _update_answer_with_fallback(supabase, ans['answer_id'], update_data)
                graded_answers.append({
                    'answer_id': ans.get('answer_id'),
                    'score': grading['score'],
                    'max_score': grading['max_score'],
                    'confidence': grading['confidence'],
                    'review_status': grading['review_status'],
                    'feedback': grading['feedback'].get('feedback', '') if isinstance(grading.get('feedback'), dict) else ''
                })
                total_marks += grading['score']
                total_max += grading['max_score']
            except Exception as e:
                logger.error("Error grading answer: %s", e)
                graded_answers.append({
                    'answer_id': ans.get('answer_id'),
                    'error': str(e)
                })
        pending_answers = sum(1 for r in graded_answers if r.get('review_status') == 'pending')
        # Update exam attempt with total score
        if attempt_id:
            try:
                recalc = _recalculate_attempt_totals(supabase, attempt_id)
                if recalc:
                    total_marks = recalc['total_marks']
                    total_max = recalc['total_max']
            except Exception as e:
                logger.error("Error updating attempt: %s", e)
       
        logger.info("Batch grading complete: %s/%s", total_marks, total_max)
       
        return jsonify({
            'success': True,
            'message': f'Graded {len(graded_answers)} answers',
            'results': graded_answers,
            'summary': {
                'total_marks': total_marks,
                'total_max': total_max,
                'percentage': round((total_marks / total_max * 100) if total_max > 0 else 0, 2),
                'pending_count': pending_answers
            }
        }), 200
       
    except Exception as e:
        logger.error("Error in grade_batch: %s", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ==========================================
# ROUTE 4.25: Create / Resume Exam Attempt
# ==========================================
@app.route('/api/attempts/create', methods=['POST'])
def create_or_resume_attempt():
    """
    Create or resume a student attempt through the backend so frontend RLS
    restrictions do not block the take-exam flow.

    Request JSON:
      {
        "exam_id": "uuid",
        "student_id": "uuid",
        "max_score": 100
      }
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('student')
        if auth_error:
            return auth_error
        data = request.json or {}
        exam_id = data.get('exam_id')
        student_id = data.get('student_id')
        max_score = data.get('max_score')
        current_user_id = _user_ctx_profile_id(user_ctx)

        if not exam_id:
            return jsonify({'error': 'exam_id is required'}), 400
        # Validate UUID format to avoid DB errors
        if not _is_valid_uuid(exam_id):
            return jsonify({'error': 'exam_id must be a valid UUID'}), 400
        if student_id and str(student_id) != str(current_user_id):
            return jsonify({'error': 'Forbidden: student identity mismatch'}), 403
        if not current_user_id:
            return jsonify({'error': 'Authenticated student profile is missing a valid user id'}), 403

        supabase = get_supabase()
        exam_row = _load_exam_row(supabase, exam_id, 'exam_id,id,status,is_visible_to_students,total_marks,course_id,exam_start_time,exam_end_time')
        if not exam_row:
            return jsonify({'error': 'Exam not found'}), 404
        if not _student_can_access_exam(supabase, user_ctx, exam_row):
            return jsonify({'error': 'Forbidden: exam is not available to students'}), 403

        # ── Scheduling enforcement ────────────────────────────────────
        import datetime as _dt
        _now = _dt.datetime.now(_dt.timezone.utc)
        _start_raw = exam_row.get('exam_start_time')
        _end_raw = exam_row.get('exam_end_time')
        if _start_raw:
            try:
                _start_str = str(_start_raw).replace('Z', '+00:00')
                if '+' not in _start_str and 'T' in _start_str:
                    _start_str += '+00:00'
                _start_dt = _dt.datetime.fromisoformat(_start_str.replace(' ', 'T'))
                if _start_dt.tzinfo is None:
                    _start_dt = _start_dt.replace(tzinfo=_dt.timezone.utc)
                if _now < _start_dt:
                    _fmt = _start_dt.strftime('%Y-%m-%d %H:%M UTC')
                    return jsonify({'error': f'Exam has not started yet. Starts at {_fmt}'}), 403
            except Exception:
                pass
        if _end_raw:
            try:
                _end_str = str(_end_raw).replace('Z', '+00:00')
                if '+' not in _end_str and 'T' in _end_str:
                    _end_str += '+00:00'
                _end_dt = _dt.datetime.fromisoformat(_end_str.replace(' ', 'T'))
                if _end_dt.tzinfo is None:
                    _end_dt = _end_dt.replace(tzinfo=_dt.timezone.utc)
                if _now > _end_dt:
                    return jsonify({'error': 'Exam has ended'}), 403
            except Exception:
                pass

        existing_resp = db_exec(lambda: supabase.table('exam_attempts').select('*')
            .eq('exam_id', exam_id)
            .eq('student_id', current_user_id)
            .eq('status', 'in_progress')
            .order('started_at', desc=True)
            .limit(1)
            .execute())

        if existing_resp.data:
            attempt = existing_resp.data[0]
            exam_full = _load_exam_row(supabase, exam_id, 'exam_id,duration_minutes,max_attempts')
            duration_minutes = int((exam_full or {}).get('duration_minutes') or 60)
            return jsonify({
                'success': True,
                'attempt_id': attempt.get('attempt_id'),
                'started_at': attempt.get('started_at'),
                'status': attempt.get('status') or 'in_progress',
                'resumed': True,
                'duration_minutes': duration_minutes
            }), 200

        # ── Max attempts enforcement ──────────────────────────────────
        try:
            exam_full_ma = _load_exam_row(supabase, exam_id, 'exam_id,duration_minutes,max_attempts')
            max_attempts_allowed = int((exam_full_ma or {}).get('max_attempts') or 1)
        except Exception:
            exam_full_ma = _load_exam_row(supabase, exam_id, 'exam_id,duration_minutes')
            max_attempts_allowed = 1
        if max_attempts_allowed > 0:
            all_attempts_resp = db_exec(lambda: supabase.table('exam_attempts').select('attempt_id,status').eq('exam_id', exam_id).eq('student_id', current_user_id).execute())
            completed_attempts = [a for a in (all_attempts_resp.data or []) if str(a.get('status') or '').lower() in ('submitted', 'graded', 'pending_grading', 'completed')]
            if len(completed_attempts) >= max_attempts_allowed:
                return jsonify({'error': f'You have already used all {max_attempts_allowed} attempt(s) for this exam.'}), 403

        safe_max_score = max_score
        try:
            safe_max_score = int(round(float(max_score))) if max_score is not None else None
        except Exception:
            safe_max_score = None

        if safe_max_score is None:
            try:
                safe_max_score = int(round(float(exam_row.get('total_marks') or 0)))
            except Exception:
                safe_max_score = 0

        payload = {
            'exam_id': exam_id,
            'student_id': current_user_id,
            'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'in_progress',
            'max_score': safe_max_score or 0
        }
        insert_resp = db_exec(lambda: supabase.table('exam_attempts').insert(payload).execute())
        if not insert_resp.data:
            return jsonify({'error': 'Failed to create attempt'}), 500

        attempt = insert_resp.data[0]
        # Return duration so frontend can sync timer with server
        exam_full = _load_exam_row(supabase, exam_id, 'exam_id,duration_minutes')
        duration_minutes = int((exam_full or {}).get('duration_minutes') or 60)
        return jsonify({
            'success': True,
            'attempt_id': attempt.get('attempt_id'),
            'started_at': attempt.get('started_at'),
            'status': attempt.get('status') or 'in_progress',
            'resumed': False,
            'duration_minutes': duration_minutes
        }), 201
    except Exception as e:
        logger.error("Error creating attempt: %s", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ==========================================
# ROUTE 4.2: Check Attempt Timer Status
# ==========================================
@app.route('/api/attempts/<attempt_id>/timer', methods=['GET'])
def check_attempt_timer(attempt_id):
    """
    Returns remaining seconds for an in-progress attempt.
    Frontend polls this every 30s to sync server time.
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('student', 'teacher', 'admin')
        if auth_error:
            return auth_error
        supabase = get_supabase()
        attempt = _load_attempt_row(supabase, attempt_id, 'attempt_id,exam_id,student_id,started_at,status')
        if not attempt:
            return jsonify({'error': 'Attempt not found'}), 404
        # Students can only check their own attempt; teachers/admins can check any
        role = str(user_ctx.get('role') or '').strip().lower()
        if role == 'student' and str(attempt.get('student_id') or '') != str(_user_ctx_profile_id(user_ctx)):
            return jsonify({'error': 'Forbidden'}), 403

        exam = _load_exam_row(supabase, attempt.get('exam_id'), 'exam_id,duration_minutes')
        duration_minutes = int((exam or {}).get('duration_minutes') or 0)

        if duration_minutes <= 0:
            return jsonify({'success': True, 'remaining_seconds': None, 'expired': False}), 200

        import datetime as _dt
        started_raw = str(attempt.get('started_at') or '').replace('Z', '+00:00')
        if '+' not in started_raw and 'T' in started_raw:
            started_raw += '+00:00'
        started_dt = _dt.datetime.fromisoformat(started_raw.replace(' ', 'T'))
        if started_dt.tzinfo is None:
            started_dt = started_dt.replace(tzinfo=_dt.timezone.utc)
        elapsed = (_dt.datetime.now(_dt.timezone.utc) - started_dt).total_seconds()
        remaining = max(0, duration_minutes * 60 - elapsed)
        expired = remaining <= 0

        return jsonify({
            'success': True,
            'remaining_seconds': int(remaining),
            'elapsed_seconds': int(elapsed),
            'duration_seconds': duration_minutes * 60,
            'expired': expired
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# ROUTE 4.3: Save Student Answers
# ==========================================
@app.route('/api/attempts/<attempt_id>/answers', methods=['POST'])
def save_attempt_answers(attempt_id):
    """
    Persist student answers for an in-progress attempt using backend service role.

    Request JSON:
      {
        "answers": [
          { "question_id": "uuid", "student_answer": "..." }
        ]
      }
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('student')
        if auth_error:
            return auth_error
        data = request.json or {}
        answers = data.get('answers') or []
        current_user_id = _user_ctx_profile_id(user_ctx)

        if not attempt_id:
            return jsonify({'error': 'attempt_id is required'}), 400
        if not isinstance(answers, list):
            return jsonify({'error': 'answers must be an array'}), 400

        supabase = get_supabase()
        attempt_row = _load_attempt_row(supabase, attempt_id, 'attempt_id,exam_id,student_id,status')
        if not attempt_row:
            return jsonify({'error': 'Attempt not found'}), 404
        if str(attempt_row.get('student_id') or '') != str(current_user_id):
            return jsonify({'error': 'Forbidden: attempt does not belong to this student'}), 403
        if str(attempt_row.get('status') or '').strip().lower() not in ('in_progress', 'submitted'):
            return jsonify({'error': 'Attempt can no longer be edited'}), 400

        exam_id = attempt_row.get('exam_id')
        exam_row = _load_exam_row(
            supabase,
            exam_id,
            'exam_id,id,status,is_visible_to_students,course_id'
        )
        if not exam_row:
            return jsonify({'error': 'Exam not found'}), 404
        if not _student_can_access_exam(supabase, user_ctx, exam_row):
            return jsonify({'error': 'Forbidden: exam is not available to this student'}), 403

        question_resp = db_exec(lambda: supabase.table('questions').select('question_id,marks').eq('exam_id', exam_id).execute())
        question_meta = {
            str(q.get('question_id')): int(round(float(q.get('marks') or 1)))
            for q in (question_resp.data or [])
            if q.get('question_id')
        }

        saved = 0
        for item in answers:
            question_id = item.get('question_id')
            if not question_id:
                continue
            payload = {
                'attempt_id': attempt_id,
                'question_id': question_id,
                'student_answer': item.get('student_answer') or '',
                'max_marks': question_meta.get(str(question_id), 1)
            }
            db_exec(lambda payload=payload: supabase.table('student_answers').upsert(
                payload,
                on_conflict='attempt_id,question_id'
            ).execute())
            saved += 1

        return jsonify({
            'success': True,
            'attempt_id': attempt_id,
            'saved_answers': saved
        }), 200
    except Exception as e:
        logger.error("Error saving student answers: %s", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ==========================================
# ROUTE 4.5: Submit Attempt + Auto Grade
# ==========================================
@app.route('/api/submit-attempt', methods=['POST'])
def submit_attempt():
    """
    Finalize a student's attempt and grade answers on server-side.

    Request JSON:
      {
        "attempt_id": "uuid",
        "time_taken_minutes": 42,
        "tab_switches": 0
      }
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('student')
        if auth_error:
            return auth_error
        data = request.json or {}
        attempt_id = data.get('attempt_id')
        time_taken_minutes = data.get('time_taken_minutes')
        tab_switches = data.get('tab_switches')
        current_user_id = _user_ctx_profile_id(user_ctx)

        if not attempt_id:
            return jsonify({'error': 'attempt_id is required'}), 400

        supabase = get_supabase()

        attempt = _load_attempt_row(supabase, attempt_id, '*')
        if not attempt:
            return jsonify({'error': 'Attempt not found'}), 404
        if str(attempt.get('student_id') or '') != str(current_user_id):
            return jsonify({'error': 'Forbidden: attempt does not belong to this student'}), 403
        exam_id = attempt.get('exam_id')
        if not exam_id:
            return jsonify({'error': 'Attempt is missing exam_id'}), 400

        exam_resp = db_exec(lambda: supabase.table('exams').select('*').eq('exam_id', exam_id).limit(1).execute())
        if not exam_resp.data:
            exam_resp = db_exec(lambda: supabase.table('exams').select('*').eq('id', exam_id).limit(1).execute())
        exam_row = exam_resp.data[0] if exam_resp.data else {}
        if not exam_row:
            return jsonify({'error': 'Exam not found'}), 404
        if not _student_can_access_exam(supabase, user_ctx, exam_row):
            return jsonify({'error': 'Forbidden: exam is not available to this student'}), 403

        # ── Server-side timer enforcement ─────────────────────────────
        duration_minutes = int(exam_row.get('duration_minutes') or 0)
        if duration_minutes > 0:
            started_raw = attempt.get('started_at') or ''
            if started_raw:
                try:
                    import datetime as _dt
                    # Parse started_at (handles both space and T separator)
                    started_str = str(started_raw).replace('Z', '+00:00')
                    if '+' not in started_str and 'T' in started_str:
                        started_str += '+00:00'
                    started_dt = _dt.datetime.fromisoformat(started_str.replace(' ', 'T'))
                    if started_dt.tzinfo is None:
                        started_dt = started_dt.replace(tzinfo=_dt.timezone.utc)
                    now_dt = _dt.datetime.now(_dt.timezone.utc)
                    elapsed_minutes = (now_dt - started_dt).total_seconds() / 60
                    # Allow 2-minute grace period for network latency
                    if elapsed_minutes > duration_minutes + 2:
                        logger.warning("[timer] Attempt %s exceeded time limit (%.1fm > %dm) — auto-submitting",
                                       attempt_id, elapsed_minutes, duration_minutes)
                        # Mark as time_expired so frontend can show the right message
                        data['time_expired'] = True
                except Exception as timer_err:
                    logger.warning("[timer] Could not check elapsed time: %s", timer_err)
        grading_mode = str(
            exam_row.get('subjective_grading_mode')
            or exam_row.get('grading_mode')
            or 'teacher'
        ).strip().lower()

        q_resp = db_exec(lambda: supabase.table('questions').select(
            'question_id,question_type,marks,options,correct_answer,question_text,model_answer,explanation'
        ).eq('exam_id', exam_id).order('question_order').execute())
        question_rows = q_resp.data or []
        # Sort MCQ → Short → Long
        _TP = {'mcq': 0, 'true_false': 1, 'short_answer': 2, 'long_answer': 3, 'essay': 4}
        question_rows = sorted(question_rows, key=lambda r: (_TP.get(str(r.get('question_type') or '').lower().replace(' ', '_'), 5), int(r.get('question_order') or 999)))
        if not question_rows:
            return jsonify({'error': 'No questions found for this exam'}), 400
        q_by_id = {q.get('question_id'): q for q in question_rows if q.get('question_id')}

        ans_resp = db_exec(lambda: supabase.table('student_answers').select(
            'answer_id,question_id,student_answer,max_marks'
        ).eq('attempt_id', attempt_id).execute())
        answers = ans_resp.data or []
        ans_by_qid = {a.get('question_id'): a for a in answers if a.get('question_id')}

        # Ensure row exists for every exam question so totals are consistent.
        for q in question_rows:
            qid = q.get('question_id')
            if not qid or qid in ans_by_qid:
                continue
            max_marks = int(round(float(q.get('marks') or 1)))
            insert_payload = {
                'attempt_id': attempt_id,
                'question_id': qid,
                'student_answer': '',
                'marks_obtained': 0,
                'max_marks': max_marks
            }
            ins = db_exec(lambda: supabase.table('student_answers').insert(insert_payload).execute())
            if ins.data:
                ans_by_qid[qid] = ins.data[0]

        graded_count = 0
        pending_count = 0
        objective_count = 0
        subjective_count = 0

        for qid, q in q_by_id.items():
            answer_row = ans_by_qid.get(qid)
            if not answer_row:
                continue
            answer_id = answer_row.get('answer_id')
            student_answer = answer_row.get('student_answer') or ''
            q_type = to_db_question_type(q.get('question_type'))
            max_marks = float(q.get('marks') or answer_row.get('max_marks') or 1)

            if q_type in ('mcq', 'true_false'):
                objective_count += 1
                correct = _is_objective_correct(
                    student_answer=student_answer,
                    correct_answer=q.get('correct_answer'),
                    options=q.get('options'),
                )
                obtained = max_marks if correct else 0.0
                update_data = {
                    'max_marks': max_marks,
                    'marks_obtained': round(obtained, 2),
                    'is_correct': bool(correct),
                    'review_status': 'auto_graded',
                    'is_manually_graded': False,
                    'ai_score': round(obtained, 2),
                    'similarity_with_model': 1.0 if correct else 0.0
                }
                _update_answer_with_fallback(supabase, answer_id, update_data)
                graded_count += 1
                continue

            # Subjective (short/long/code/essay)
            subjective_count += 1
            question_text = q.get('question_text') or ''
            reference_answer = q.get('model_answer') or q.get('correct_answer') or q.get('explanation') or ''
            normalized = _normalize_grading_result(
                _grade_essay_flex(
                    question_text=question_text,
                    reference_answer=reference_answer,
                    student_answer=student_answer,
                    max_marks=max_marks
                ),
                max_marks=max_marks
            )

            if not str(student_answer).strip():
                review_status = 'auto_graded'
                obtained = 0.0
                is_correct = False
            elif grading_mode == 'teacher':
                # Teacher-first mode: keep AI marks as suggestion but require manual review.
                review_status = 'pending'
                obtained = float(normalized.get('score') or 0)
                is_correct = None
            else:
                # model/hybrid mode: auto-grade when confidence is enough.
                review_status = normalized.get('review_status') or 'pending'
                obtained = float(normalized.get('score') or 0)
                is_correct = None if review_status == 'pending' else bool(obtained > 0)

            update_data = {
                'max_marks': max_marks,
                'marks_obtained': round(max(0.0, min(obtained, max_marks)), 2),
                'ai_score': round(float(normalized.get('score') or 0), 2),
                'similarity_with_model': float(normalized.get('confidence') or 0),
                'review_status': review_status,
                'is_manually_graded': False,
                'is_correct': is_correct,
                'ai_feedback': normalized.get('feedback')
            }
            _update_answer_with_fallback(supabase, answer_id, update_data)
            graded_count += 1
            if review_status == 'pending':
                pending_count += 1

        summary = _recalculate_attempt_totals(supabase, attempt_id) or {}
        attempt_update = {}
        if time_taken_minutes is not None:
            try:
                attempt_update['time_taken_minutes'] = max(0, int(time_taken_minutes))
            except Exception:
                pass
        if tab_switches is not None:
            try:
                attempt_update['tab_switches'] = max(0, int(tab_switches))
            except Exception:
                pass
        attempt_update['submitted_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        # Keep "submitted" wording in UI where pending exists.
        attempt_update['status'] = 'submitted' if summary.get('pending_count', 0) > 0 else 'graded'
        attempt_update['is_graded'] = bool(attempt_update['status'] == 'graded')
        if attempt_update['status'] == 'graded':
            attempt_update['graded_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        db_exec(lambda: supabase.table('exam_attempts').update(attempt_update).eq('attempt_id', attempt_id).execute())

        # Recompute once more after final status update.
        summary = _recalculate_attempt_totals(supabase, attempt_id) or summary

        logger.info(f"Attempt {attempt_id} submitted: auto={objective_count} pending={pending_count}")
        return jsonify({
            'success': True,
            'message': 'Attempt submitted and graded',
            'attempt_id': attempt_id,
            'grading_mode': grading_mode,
            'summary': summary,
            'details': {
                'graded_count': graded_count,
                'pending_count': pending_count,
                'objective_count': objective_count,
                'subjective_count': subjective_count
            }
        }), 200
    except Exception as e:
        logger.error("Error in submit_attempt: %s", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
# ==========================================
# ROUTE 5: Teacher Manual Grade
# ==========================================
@app.route('/api/teacher-grade', methods=['POST'])
def teacher_grade():
    """
    Teacher manual grading for one answer.
    Request JSON:
    {
      "answer_id": "uuid",
      "marks_obtained": 3,
      "teacher_remarks": "Good attempt",
      "publish_result": false,
      "teacher_id": "uuid" (optional ownership check)
    }
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        data = request.json or {}
        answer_id = data.get('answer_id')
        marks_obtained = data.get('marks_obtained')
        teacher_remarks = data.get('teacher_remarks')
        publish_result = bool(data.get('publish_result'))
        requester_teacher_id = _user_ctx_profile_id(user_ctx)
        if not answer_id:
            return jsonify({'error': 'answer_id is required'}), 400
        if marks_obtained is None:
            return jsonify({'error': 'marks_obtained is required'}), 400
        supabase = get_supabase()
        ans_resp = supabase.table('student_answers').select(
            'answer_id,attempt_id,max_marks'
        ).eq('answer_id', answer_id).limit(1).execute()
        if not ans_resp.data:
            return jsonify({'error': 'Answer not found'}), 404
        answer_row = ans_resp.data[0]
        attempt_id = answer_row.get('attempt_id')
        max_marks = float(answer_row.get('max_marks') or 0)
        try:
            marks = float(marks_obtained)
        except Exception:
            return jsonify({'error': 'marks_obtained must be numeric'}), 400
        if max_marks > 0:
            marks = max(0.0, min(marks, max_marks))
        else:
            marks = max(0.0, marks)
        if attempt_id:
            attempt_row = _load_attempt_row(supabase, attempt_id, 'attempt_id,exam_id')
            if not attempt_row:
                return jsonify({'error': 'Attempt not found'}), 404
            exam_auth_error = _require_teacher_exam_owner(supabase, attempt_row.get('exam_id'), user_ctx)[1]
            if exam_auth_error:
                return exam_auth_error
        update_data = {
            'marks_obtained': round(marks, 2),
            'teacher_marks': round(marks, 2),
            'teacher_remarks': _sanitize_text(teacher_remarks),
            'is_manually_graded': True,
            'review_status': 'teacher_graded'
        }
        if max_marks > 0:
            update_data['is_correct'] = bool(marks >= max_marks)
        else:
            update_data['is_correct'] = bool(marks > 0)
        _update_answer_with_fallback(supabase, answer_id, update_data)
        summary = _recalculate_attempt_totals(supabase, attempt_id) if attempt_id else None
        if attempt_id and summary:
            attempt_status = 'graded' if publish_result and summary.get('pending_count', 0) == 0 else 'pending_grading'
            attempt_update = {
                'status': attempt_status,
                'is_graded': bool(attempt_status == 'graded'),
                'updated_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            if attempt_status == 'graded':
                attempt_update['graded_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
                if requester_teacher_id:
                    attempt_update['graded_by'] = requester_teacher_id
            else:
                attempt_update['graded_at'] = None
                attempt_update['graded_by'] = None
            supabase.table('exam_attempts').update(attempt_update).eq('attempt_id', attempt_id).execute()
            summary['status'] = attempt_status
        logger.info(f"Teacher graded answer {answer_id}: {marks}/{max_marks}")
        return jsonify({
            'success': True,
            'message': 'Manual grade saved',
            'answer_id': answer_id,
            'attempt_id': attempt_id,
            'summary': summary
        }), 200
    except Exception as e:
        logger.error("Error in teacher_grade: %s", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/publish-result', methods=['POST'])
def publish_result():
    """
    Finalize and publish a reviewed attempt so students see final marks/grade.
    Request JSON:
    {
      "attempt_id": "uuid",
      "teacher_id": "uuid" (optional ownership check)
    }
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        data = request.json or {}
        attempt_id = data.get('attempt_id')
        requester_teacher_id = _user_ctx_profile_id(user_ctx)
        if not attempt_id:
            return jsonify({'error': 'attempt_id is required'}), 400

        supabase = get_supabase()
        attempt_row = _load_attempt_row(supabase, attempt_id, 'attempt_id,exam_id')
        if not attempt_row:
            return jsonify({'error': 'Attempt not found'}), 404

        exam_id_for_attempt = attempt_row.get('exam_id')
        _, exam_auth_error = _require_teacher_exam_owner(supabase, exam_id_for_attempt, user_ctx)
        if exam_auth_error:
            return exam_auth_error

        summary = _recalculate_attempt_totals(supabase, attempt_id) or {}
        if summary.get('pending_count', 0) > 0:
            return jsonify({
                'success': False,
                'error': 'All pending answers must be reviewed before publishing results.',
                'summary': summary
            }), 400

        attempt_update = {
            'status': 'graded',
            'is_graded': True,
            'graded_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        if requester_teacher_id:
            attempt_update['graded_by'] = requester_teacher_id
        supabase.table('exam_attempts').update(attempt_update).eq('attempt_id', attempt_id).execute()
        summary['status'] = 'graded'

        # ── Email: notify student that result is ready ─────────────
        try:
            from utils.email_notify import notify_result_ready
            att_row = _load_attempt_row(supabase, attempt_id, 'student_id,score,max_score,percentage,exam_id')
            if att_row:
                student_r = db_exec(lambda: supabase.table('users').select(
                    'email,first_name,last_name'
                ).eq('id', att_row.get('student_id')).limit(1).execute())
                exam_r = _load_exam_row(supabase, att_row.get('exam_id'), 'exam_id,exam_title')
                if student_r.data:
                    s = student_r.data[0]
                    s_name = f"{s.get('first_name','')} {s.get('last_name','')}".strip() or 'Student'
                    import threading
                    threading.Thread(
                        target=notify_result_ready,
                        args=(
                            s.get('email', ''), s_name,
                            (exam_r or {}).get('exam_title', 'Exam'),
                            float(att_row.get('score') or 0),
                            float(att_row.get('max_score') or 0),
                            float(att_row.get('percentage') or 0),
                            attempt_id
                        ),
                        daemon=True
                    ).start()
        except Exception as email_err:
            logger.warning("[email] Result notification failed: %s", email_err)

        return jsonify({
            'success': True,
            'message': 'Result published successfully',
            'attempt_id': attempt_id,
            'summary': summary
        }), 200
    except Exception as e:
        logger.error("Error in publish_result: %s", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
# ==========================================
# ROUTE 5: Extract Topics Only
# ==========================================
@app.route('/api/extract-topics', methods=['POST'])
def extract_topics():
    """
    Extract topics from uploaded file
   
    Request:
        - file: PDF/DOCX file
        - num_topics: Number of topics (default: 5)
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
       
        file = request.files['file']
       
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type'}), 400
       
        num_topics = int(request.form.get('num_topics', 5))
       
        # Save file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
       
        # Extract text
        text = extract_text_from_file(filepath)
       
        if not text:
            return jsonify({'error': 'Failed to extract text'}), 500
       
        # Extract topics (BERTopic)
        topics = extract_topics_from_text(text, num_topics)
        # Classify subject (DistilBERT)
        subject_info = classify_subject(text[:3000])
        # Classify code concept (CodeBERT) — when code is detected
        code_concept = None
        import re as _re_tmp
        _code_patterns = [r'def\s+\w+\s*\(', r'class\s+\w+', r'SELECT\b', r'function\s+\w+']
        if any(_re_tmp.search(p, text, _re_tmp.IGNORECASE) for p in _code_patterns):
            code_concept = classify_code_concept(text[:2048])
        return jsonify({
            'success': True,
            'topics': topics,
            'subject': subject_info,
            'code_concept': code_concept,
            'text_length': len(text)
        }), 200
       
    except Exception as e:
        logger.error("Error: %s", e)
        return jsonify({'error': str(e)}), 500
# ==========================================
# ROUTE 6: Get Model Info
# ==========================================
@app.route('/api/models/info', methods=['GET'])
def model_info():
    """Get information about loaded AI models — public endpoint"""
    return jsonify({
        'models': {
            'question_generator': {
                'name': 'Ollama Qwen 2.5 7B',
                'type': 'Text Generation (Ollama)',
                'purpose': 'Generate exam questions from text',
                'subjects': [
                    'python_programming',
                    'database_fundamentals',
                    'web_development',
                    'software_engineering',
                    'object_oriented_programming'
                ]
            },
            'essay_grader': {
                'name': 'Sentence-BERT',
                'type': 'Semantic Similarity',
                'purpose': 'Grade subjective answers',
                'features': [
                    'Similarity scoring',
                    'Concept coverage',
                    'Quality analysis'
                ]
            },
            'topic_extractor': {
                'name': 'BERTopic',
                'type': 'Topic Modeling',
                'purpose': 'Extract main topics from documents'
            },
            'subject_classifier': {
                'name': 'DistilBERT',
                'type': 'Sequence Classification',
                'purpose': 'Classify text into one of 5 academic subjects'
            },
            'code_analyzer': {
                'name': 'CodeBERT',
                'type': 'Code Understanding',
                'purpose': 'Analyse code snippets and classify programming concepts'
            },
            'question_generator_alt': {
                'name': 'Qwen LoRA',
                'type': 'Text Generation (GPU only)',
                'purpose': 'High-quality question generation on GPU hardware'
            }
        }
    }), 200
# ==========================================
# ROUTE 7: List Submissions
# ==========================================
@app.route('/api/submissions', methods=['GET', 'OPTIONS'])
def list_submissions():
    """
    List exam submissions for dashboard.
    Optional query params:
        teacher_id: Filter submissions to exams owned by this teacher
        status: comma-separated statuses (default: submitted,graded)
        limit: max rows (default: 100)
    """
    try:
        if request.method == 'OPTIONS':
            return ('', 204)
        user_ctx, auth_error = _require_authenticated_user()
        if auth_error:
            return auth_error
        supabase = get_supabase()
        role = str(user_ctx.get('role') or '').strip().lower()
        if str(user_ctx.get('status') or '').strip().lower() != 'active':
            return jsonify({'success': False, 'error': 'Active account required', 'submissions': []}), 403
        current_user_id = _user_ctx_profile_id(user_ctx)
        teacher_id = request.args.get('teacher_id')
        student_id = request.args.get('student_id')
        status_param = request.args.get('status', 'submitted,pending_grading,graded')
        statuses = [s.strip() for s in status_param.split(',') if s.strip()]
        limit_raw = request.args.get('limit', '100')
        try:
            limit_val = max(1, min(int(limit_raw), 500))
        except Exception:
            limit_val = 100
        query = supabase.table('exam_attempts').select('*')
        if statuses:
            query = query.in_('status', statuses)
        if role == 'student':
            if student_id and str(student_id) != str(current_user_id):
                return jsonify({'success': False, 'error': 'Forbidden: student filter does not match authenticated user', 'submissions': []}), 403
            query = query.eq('student_id', current_user_id)
        elif role == 'teacher':
            if teacher_id and str(teacher_id) != str(current_user_id):
                return jsonify({'success': False, 'error': 'Forbidden: teacher filter does not match authenticated user', 'submissions': []}), 403
        elif role == 'admin':
            if student_id:
                query = query.eq('student_id', student_id)
        else:
            return jsonify({'success': False, 'error': 'Forbidden: unsupported role', 'submissions': []}), 403
        if role != 'student' and student_id and role == 'admin':
            query = query.eq('student_id', student_id)
        attempts_resp = query.order('submitted_at', desc=True).limit(limit_val).execute()
        attempts = attempts_resp.data if attempts_resp.data else []
        # Filter by teacher exam ownership.
        if role == 'teacher':
            exams_resp = supabase.table('exams').select('exam_id, id').eq('teacher_id', current_user_id).execute()
            exams = exams_resp.data if exams_resp.data else []
            teacher_exam_ids = {
                (e.get('exam_id') or e.get('id'))
                for e in exams
                if (e.get('exam_id') or e.get('id'))
            }
            attempts = [a for a in attempts if a.get('exam_id') in teacher_exam_ids]
        elif role == 'admin' and teacher_id and attempts:
            exams_resp = supabase.table('exams').select('exam_id, id').eq('teacher_id', teacher_id).execute()
            exams = exams_resp.data if exams_resp.data else []
            teacher_exam_ids = {
                (e.get('exam_id') or e.get('id'))
                for e in exams
                if (e.get('exam_id') or e.get('id'))
            }
            attempts = [a for a in attempts if a.get('exam_id') in teacher_exam_ids]
        exam_ids = [a.get('exam_id') for a in attempts if a.get('exam_id')]
        exam_meta = {}
        if exam_ids:
            try:
                ex_resp = supabase.table('exams').select('exam_id,id,exam_title,total_marks').in_('exam_id', exam_ids).execute()
                for e in (ex_resp.data or []):
                    ex_id = e.get('exam_id') or e.get('id')
                    if ex_id:
                        exam_meta[str(ex_id)] = e
                # Fallback for schemas where attempts reference exams.id
                missing = [eid for eid in exam_ids if str(eid) not in exam_meta]
                if missing:
                    ex_resp2 = supabase.table('exams').select('exam_id,id,exam_title,total_marks').in_('id', missing).execute()
                    for e in (ex_resp2.data or []):
                        ex_id = e.get('exam_id') or e.get('id')
                        if ex_id:
                            exam_meta[str(ex_id)] = e
            except Exception as meta_err:
                logger.warning("Could not enrich submissions with exam metadata: %s", meta_err)
        submissions = []
        for a in attempts:
            ex_id = a.get('exam_id')
            ex = exam_meta.get(str(ex_id), {})
            submissions.append({
                'submission_id': a.get('attempt_id') or a.get('submission_id'),
                'attempt_id': a.get('attempt_id'),
                'exam_id': ex_id,
                'exam_title': ex.get('exam_title') or 'Exam',
                'total_marks': ex.get('total_marks'),
                'student_id': a.get('student_id'),
                'score': a.get('score') or a.get('marks_obtained') or 0,
                'percentage': a.get('percentage'),
                'submitted_at': a.get('submitted_at') or a.get('updated_at') or a.get('created_at'),
                'graded_at': a.get('graded_at'),
                'status': a.get('status') or 'submitted'
            })
        return jsonify({
            'success': True,
            'count': len(submissions),
            'submissions': submissions
        }), 200
    except Exception as e:
        logger.error("Error listing submissions: %s", e)
        return jsonify({'success': False, 'error': str(e), 'submissions': []}), 500
# ==========================================
# ROUTE 7.5: Attempt Results
# ==========================================
@app.route('/api/attempt-results/<attempt_id>', methods=['GET'])
def get_attempt_results(attempt_id):
    """
    Return one attempt plus answer/question detail for results/review pages.
    Access rules:
      - student can only view own attempt
      - teacher can only view attempts for their exam
      - admin can view any attempt
    """
    try:
        # Validate UUID format early to avoid DB errors
        if not _is_valid_uuid(attempt_id):
            return jsonify({'success': False, 'error': 'Attempt not found'}), 404

        user_ctx, auth_error = _require_authenticated_user()
        if auth_error:
            return auth_error
        requester_user_id = _user_ctx_profile_id(user_ctx)
        requester_role = str(user_ctx.get('role') or '').strip().lower()
        if str(user_ctx.get('status') or '').strip().lower() != 'active':
            return jsonify({'success': False, 'error': 'Active account required'}), 403

        supabase = get_supabase()
        attempt = _load_attempt_row(supabase, attempt_id, '*')
        if not attempt:
            return jsonify({'success': False, 'error': 'Attempt not found'}), 404

        exam_id = attempt.get('exam_id')

        exam = {}
        if exam_id:
            exam = _load_exam_row(
                supabase,
                exam_id,
                'exam_id,id,exam_title,title,total_marks,duration_minutes,teacher_id,status,is_visible_to_students'
            ) or {}
            if exam and not exam.get('exam_title') and exam.get('title'):
                exam['exam_title'] = exam.get('title')

        if requester_role == 'student':
            if requester_user_id and attempt.get('student_id') and str(attempt.get('student_id')) != str(requester_user_id):
                return jsonify({'success': False, 'error': 'Forbidden: attempt does not belong to this student'}), 403
            attempt_status = str(attempt.get('status') or '').strip().lower()
            if attempt_status not in ('graded', 'completed'):
                return jsonify({
                    'success': False,
                    'error': 'Results are pending teacher review',
                    'status': attempt_status
                }), 403
        elif requester_role == 'teacher':
            if requester_user_id and exam.get('teacher_id') and str(exam.get('teacher_id')) != str(requester_user_id):
                return jsonify({'success': False, 'error': 'Forbidden: attempt does not belong to this teacher'}), 403
        elif requester_role != 'admin':
            return jsonify({'success': False, 'error': 'Forbidden: unsupported role'}), 403

        question_rows = []
        if exam_id:
            q_resp = db_exec(lambda: supabase.table('questions').select(
                'question_id,question_text,question_type,marks,options,correct_answer,explanation,question_order,model_answer'
            ).eq('exam_id', exam_id).order('question_order').execute())
            question_rows = q_resp.data or []
        questions_by_id = {
            str(q.get('question_id')): dict(q or {})
            for q in question_rows
            if q.get('question_id')
        }

        answers_resp = db_exec(lambda: supabase.table('student_answers').select('*').eq('attempt_id', attempt_id).execute())
        answers = []
        for answer in (answers_resp.data or []):
            answer_payload = dict(answer or {})
            question_id = answer_payload.get('question_id')
            answer_payload['questions'] = questions_by_id.get(str(question_id), {})
            answers.append(answer_payload)

        def _answer_sort_key(answer):
            question = answer.get('questions') or {}
            try:
                return int(question.get('question_order') or 999999)
            except Exception:
                return 999999

        answers.sort(key=_answer_sort_key)
        attempt['exams'] = exam

        return jsonify({
            'success': True,
            'attempt': attempt,
            'answers': answers
        }), 200
    except Exception as e:
        logger.error("Error in get_attempt_results: %s", e)
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'attempt': None, 'answers': []}), 500


# ==========================================
# ROUTE: Plagiarism Detection
# ==========================================
@app.route('/api/exams/<exam_id>/plagiarism', methods=['GET'])
def detect_plagiarism(exam_id):
    """Compare subjective answers across students. Teacher-only."""
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher', 'admin')
        if auth_error:
            return auth_error
        supabase = get_supabase()
        if user_ctx.get('role') == 'teacher':
            _, err = _require_teacher_exam_owner(supabase, exam_id, user_ctx)
            if err:
                return err
        attempts_resp = db_exec(lambda: supabase.table('exam_attempts').select('attempt_id,student_id').eq('exam_id', exam_id).in_('status', ['submitted', 'graded', 'pending_grading']).execute())
        attempts = attempts_resp.data or []
        if len(attempts) < 2:
            return jsonify({'success': True, 'flagged_pairs': [], 'message': 'Need at least 2 submissions'}), 200
        student_ids = [a.get('student_id') for a in attempts if a.get('student_id')]
        students_resp = db_exec(lambda: supabase.table('users').select('id,first_name,last_name,email').in_('id', student_ids).execute())
        student_map = {s['id']: s for s in (students_resp.data or [])}
        attempt_ids = [a.get('attempt_id') for a in attempts if a.get('attempt_id')]
        answers_resp = db_exec(lambda: supabase.table('student_answers').select('attempt_id,question_id,student_answer').in_('attempt_id', attempt_ids).execute())
        answers = answers_resp.data or []
        from collections import defaultdict
        by_question = defaultdict(list)
        for ans in answers:
            qid = ans.get('question_id')
            text = str(ans.get('student_answer') or '').strip()
            if qid and text and len(text) > 20:
                attempt_id = ans.get('attempt_id')
                sid = next((a.get('student_id') for a in attempts if a.get('attempt_id') == attempt_id), None)
                by_question[qid].append({'student_id': sid, 'attempt_id': attempt_id, 'text': text})
        flagged_pairs = []
        THRESHOLD = 0.85
        for qid, q_answers in by_question.items():
            if len(q_answers) < 2:
                continue
            for i in range(len(q_answers)):
                for j in range(i + 1, len(q_answers)):
                    a1, a2 = q_answers[i], q_answers[j]
                    if a1['student_id'] == a2['student_id']:
                        continue
                    similarity = 0.0
                    try:
                        from models.essay_grader import _try_load_sbert, _sbert_model
                        if _try_load_sbert() and _sbert_model:
                            from sentence_transformers import util
                            e1 = _sbert_model.encode(a1['text'], convert_to_tensor=True)
                            e2 = _sbert_model.encode(a2['text'], convert_to_tensor=True)
                            similarity = float(util.cos_sim(e1, e2).item())
                    except Exception:
                        w1 = set(a1['text'].lower().split())
                        w2 = set(a2['text'].lower().split())
                        if w1 and w2:
                            similarity = len(w1 & w2) / max(len(w1), len(w2))
                    if similarity >= THRESHOLD:
                        s1 = student_map.get(a1['student_id'], {})
                        s2 = student_map.get(a2['student_id'], {})
                        flagged_pairs.append({
                            'question_id': qid, 'similarity': round(similarity, 3),
                            'student_1': {'name': f"{s1.get('first_name','')} {s1.get('last_name','')}".strip() or s1.get('email',''), 'attempt_id': a1['attempt_id'], 'preview': a1['text'][:120]},
                            'student_2': {'name': f"{s2.get('first_name','')} {s2.get('last_name','')}".strip() or s2.get('email',''), 'attempt_id': a2['attempt_id'], 'preview': a2['text'][:120]}
                        })
        flagged_pairs.sort(key=lambda x: x['similarity'], reverse=True)
        return jsonify({'success': True, 'exam_id': exam_id, 'total_submissions': len(attempts), 'flagged_pairs': flagged_pairs, 'threshold': THRESHOLD}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500



# ==========================================
# ROUTE: Exam Analytics & Quality Metrics
# ==========================================
@app.route('/api/exams/<exam_id>/analytics', methods=['GET'])
def get_exam_analytics(exam_id):
    """
    Get quality and grounding analytics for an exam.
    Teacher-only: Returns grounding, duplicate risk, validation status.
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher', 'admin')
        if auth_error:
            return auth_error
        
        supabase = get_supabase()
        
        # Check ownership (teacher must own exam)
        if user_ctx.get('role') == 'teacher':
            _, err = _require_teacher_exam_owner(supabase, exam_id, user_ctx)
            if err:
                return err
        
        # Load exam
        exam = _load_exam_row(supabase, exam_id, 'exam_id,id,exam_title,subject,total_marks,exam_metadata')
        if not exam:
            return jsonify({'success': False, 'error': 'Exam not found'}), 404
        
        # Load questions with grounding/quality data
        questions_resp = db_exec(
            lambda: supabase.table('questions')
            .select('*')
            .eq('exam_id', exam_id)
            .execute()
        )
        questions = questions_resp.data or []
        
        if not questions:
            return jsonify({
                'success': True,
                'exam_id': exam_id,
                'exam_title': exam.get('exam_title'),
                'analytics': {
                    'grounding': {'total': 0, 'grounded': 0, 'confidence_avg': 0},
                    'duplicates': {'total': 0, 'high_risk': 0, 'medium_risk': 0},
                    'coverage_by_topic': [],
                    'difficulty_distribution': {},
                    'question_type_distribution': {}
                }
            }), 200
        
        # ── GROUNDING ANALYTICS ──
        grounded_count = sum(1 for q in questions if q.get('is_grounded'))
        confidence_scores = [q.get('grounding_confidence', 0) for q in questions if q.get('grounding_confidence')]
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        # ── DUPLICATE ANALYTICS ──
        high_risk_count = sum(1 for q in questions if q.get('duplicate_risk') == 'high')
        medium_risk_count = sum(1 for q in questions if q.get('duplicate_risk') == 'medium')
        
        # ── TOPIC COVERAGE ──
        topic_coverage = {}
        for q in questions:
            topic = q.get('source_section', 'Unknown')
            if topic not in topic_coverage:
                topic_coverage[topic] = {'count': 0, 'marks': 0}
            topic_coverage[topic]['count'] += 1
            topic_coverage[topic]['marks'] += q.get('marks', 0)
        
        coverage_by_topic = [
            {'topic': t, 'question_count': s['count'], 'marks': s['marks'], 
             'percentage': round(100 * s['count'] / len(questions), 1)}
            for t, s in sorted(topic_coverage.items(), key=lambda x: -x[1]['count'])
        ]
        
        # ── DIFFICULTY DISTRIBUTION ──
        difficulty_dist = {}
        for q in questions:
            diff = q.get('difficulty_level', 'medium')
            difficulty_dist[diff] = difficulty_dist.get(diff, 0) + 1
        
        # ── QUESTION TYPE DISTRIBUTION ──
        type_dist = {}
        for q in questions:
            qtype = q.get('type', 'unknown').upper()
            type_dist[qtype] = type_dist.get(qtype, 0) + 1
        
        analytics = {
            'grounding': {
                'total_questions': len(questions),
                'grounded_questions': grounded_count,
                'ungrounded_questions': len(questions) - grounded_count,
                'grounding_percentage': round(100 * grounded_count / len(questions), 1),
                'average_confidence': round(avg_confidence, 3)
            },
            'duplicates': {
                'total_questions': len(questions),
                'high_risk_count': high_risk_count,
                'medium_risk_count': medium_risk_count,
                'no_risk_count': len(questions) - high_risk_count - medium_risk_count
            },
            'coverage_by_topic': coverage_by_topic,
            'difficulty_distribution': difficulty_dist,
            'question_type_distribution': type_dist,
            'warnings': []
        }
        
        # Generate warnings
        if grounded_count < len(questions) * 0.8:
            analytics['warnings'].append(
                f"Only {grounded_count}/{len(questions)} questions grounded to source material"
            )
        if high_risk_count > 0:
            analytics['warnings'].append(
                f"{high_risk_count} questions flagged as potential duplicates"
            )
        if len(coverage_by_topic) == 1:
            analytics['warnings'].append(
                "All questions from single topic - consider more diverse coverage"
            )
        
        return jsonify({
            'success': True,
            'exam_id': exam_id,
            'exam_title': exam.get('exam_title'),
            'exam_subject': exam.get('subject'),
            'analytics': analytics
        }), 200
        
    except Exception as e:
        print(f"Error getting exam analytics: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# ROUTE: Cleanup Old Uploads
# ==========================================
@app.route('/api/admin/cleanup-uploads', methods=['POST'])
def cleanup_old_uploads():
    """Delete uploaded files older than N days. Admin only."""
    try:
        state, identity, auth_error = _require_authorized_admin()
        if auth_error:
            return auth_error
        data = request.get_json(silent=True) or {}
        days = max(1, int(data.get('days') or 30))
        import datetime as _dt
        cutoff = _dt.datetime.now() - _dt.timedelta(days=days)
        upload_dir = os.path.join(os.path.dirname(__file__), 'uploads')
        if not os.path.isdir(upload_dir):
            return jsonify({'success': True, 'deleted': 0}), 200
        deleted = 0
        freed_bytes = 0
        for fname in os.listdir(upload_dir):
            fpath = os.path.join(upload_dir, fname)
            if not os.path.isfile(fpath):
                continue
            if _dt.datetime.fromtimestamp(os.path.getmtime(fpath)) < cutoff:
                size = os.path.getsize(fpath)
                try:
                    os.remove(fpath)
                    deleted += 1
                    freed_bytes += size
                except Exception:
                    pass
        freed_mb = round(freed_bytes / (1024 * 1024), 2)
        return jsonify({'success': True, 'deleted': deleted, 'freed_mb': freed_mb, 'message': f'Deleted {deleted} files older than {days} days ({freed_mb} MB freed)'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# ROUTE 7.6: Export Result as PDF
# ==========================================
@app.route('/api/attempt-results/<attempt_id>/export-pdf', methods=['GET'])
def export_result_pdf(attempt_id):
    """Returns a printable HTML page the browser can save as PDF."""
    try:
        user_ctx, auth_error = _require_authenticated_user()
        if auth_error:
            return auth_error

        supabase = get_supabase()
        role = str((user_ctx or {}).get('role') or '').strip().lower()
        current_user_id = _user_ctx_profile_id(user_ctx)

        attempt = _load_attempt_row(supabase, attempt_id, '*')
        if not attempt:
            return jsonify({'error': 'Attempt not found'}), 404
        if role == 'student' and str(attempt.get('student_id') or '') != str(current_user_id):
            return jsonify({'error': 'Forbidden'}), 403

        exam_id = attempt.get('exam_id')
        exam    = _load_exam_row(supabase, exam_id, 'exam_id,exam_title,total_marks,duration_minutes,subject')
        exam_title = (exam or {}).get('exam_title') or 'Exam'

        student_resp = db_exec(lambda: supabase.table('users').select(
            'first_name,last_name,email,student_id'
        ).eq('id', attempt.get('student_id')).limit(1).execute())
        student     = student_resp.data[0] if student_resp.data else {}
        student_name = f"{student.get('first_name','')} {student.get('last_name','')}".strip() or 'Student'

        ans_resp = db_exec(lambda: supabase.table('student_answers').select(
            'answer_id,question_id,student_answer,marks_obtained,max_marks,is_correct,review_status,teacher_remarks'
        ).eq('attempt_id', attempt_id).execute())
        answers = ans_resp.data or []

        q_ids = [a.get('question_id') for a in answers if a.get('question_id')]
        q_map = {}
        if q_ids:
            qs_resp = db_exec(lambda: supabase.table('questions').select(
                'question_id,question_text,question_type,marks,options,correct_answer,question_order'
            ).in_('question_id', q_ids).order('question_order').execute())
            q_map = {q['question_id']: q for q in (qs_resp.data or [])}

        answers_sorted = sorted(answers, key=lambda a: int(
            (q_map.get(a.get('question_id'), {}).get('question_order') or 999)))

        score      = float(attempt.get('score') or 0)
        max_score  = float(attempt.get('max_score') or 0)
        percentage = float(attempt.get('percentage') or 0)
        submitted  = str(attempt.get('submitted_at') or attempt.get('updated_at') or '')[:19]
        att_status = str(attempt.get('status') or '')
        grade      = 'A' if percentage >= 90 else 'B' if percentage >= 80 else 'C' if percentage >= 70 else 'D' if percentage >= 60 else 'F'
        grade_color = '#059669' if percentage >= 70 else '#d97706' if percentage >= 50 else '#dc2626'

        from pdf_export import build_result_html
        html = build_result_html(
            exam_title=exam_title,
            student_name=student_name,
            student_email=student.get('email', ''),
            student_reg=student.get('student_id', ''),
            score=score, max_score=max_score,
            percentage=percentage, grade=grade, grade_color=grade_color,
            submitted=submitted, status=att_status,
            answers_sorted=answers_sorted, q_map=q_map
        )
        from flask import Response
        return Response(html, mimetype='text/html')
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ==========================================
# ROUTE 8: Grading Stats (RPC)
# ==========================================
@app.route('/api/grading-stats', methods=['GET'])
def grading_stats():
    """
    Return grading status counts using Supabase SQL RPC functions.
    Query params:
      - attempt_id (preferred for one submission)
      - exam_id (for all attempts of an exam)
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher', 'admin')
        if auth_error:
            return auth_error
        supabase = get_supabase()
        attempt_id = request.args.get('attempt_id')
        exam_id = request.args.get('exam_id')
        if not attempt_id and not exam_id:
            return jsonify({
                'success': False,
                'error': 'exam_id or attempt_id is required'
            }), 400
        rows = []
        if attempt_id:
            resp = supabase.rpc('grading_stats_by_attempt', {'p_attempt_id': attempt_id}).execute()
            rows = resp.data or []
        else:
            # Prefer full-status function if present; fallback to compact function.
            try:
                resp = supabase.rpc('grading_stats_by_exam_full', {'p_exam_id': exam_id}).execute()
                rows = resp.data or []
            except Exception:
                resp = supabase.rpc('grading_stats_by_exam', {'p_exam_id': exam_id}).execute()
                rows = resp.data or []
        counts = {}
        total = 0
        for r in rows:
            status = str(r.get('review_status') or 'unknown')
            try:
                c = int(r.get('count') or 0)
            except Exception:
                c = 0
            counts[status] = c
            total += c
        return jsonify({
            'success': True,
            'total': total,
            'counts': counts,
            'rows': rows
        }), 200
    except Exception as e:
        logger.error("Error in grading_stats: %s", e)
        return jsonify({'success': False, 'error': str(e), 'rows': []}), 500
# ==========================================
# ERROR HANDLERS
# ==========================================
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404
@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500
# ==========================================
# RUN SERVER
# ==========================================
# ==========================================
# ROUTE: Get Exam Details
# ==========================================
@app.route('/api/exam/<exam_id>', methods=['GET'])
def get_exam(exam_id):
    """Retrieve exam details from Supabase"""
    try:
        user_ctx, auth_error = _optional_authenticated_user()
        if auth_error:
            return auth_error
        supabase = get_supabase()
        exam = _load_exam_row(supabase, exam_id, '*')
        if exam:
            role = str((user_ctx or {}).get('role') or '').strip().lower()
            current_user_id = _user_ctx_profile_id(user_ctx) if user_ctx else None
            if role == 'teacher':
                owner = str(exam.get('teacher_id') or '').strip()
                if owner and owner != str(current_user_id) and not _can_student_view_exam(exam):
                    return jsonify({'status': 'forbidden', 'message': 'Exam is not available to this teacher'}), 403
            elif role == 'admin':
                if str((user_ctx or {}).get('status') or '').strip().lower() != 'active':
                    return jsonify({'status': 'forbidden', 'message': 'Active admin account required'}), 403
            else:
                if not user_ctx or user_ctx.get('role') != 'student':
                    return jsonify({'status': 'forbidden', 'message': 'Student authentication required'}), 403
                if not _student_can_access_exam(supabase, user_ctx, exam):
                    return jsonify({'status': 'forbidden', 'message': 'Exam is not available to students'}), 403
            return jsonify({
                'status': 'success',
                'exam': exam
            }), 200
       
        return jsonify({
            'status': 'not_found',
            'exam_id': exam_id,
            'message': 'Exam not found'
        }), 404
           
    except Exception as e:
        logger.error("Error retrieving exam: %s", e)
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
# ==========================================
# COMPAT ROUTE: Get Exam by /api/exams/<id>
# ==========================================
@app.route('/api/exams/<exam_id>', methods=['GET'])
def get_exam_compat(exam_id):
    """Compatibility alias for clients that call /api/exams/<exam_id>."""
    return get_exam(exam_id)
# ==========================================
# COMPAT ROUTE: Preview endpoint
# ==========================================
@app.route('/api/exams/<exam_id>/preview', methods=['GET'])
def get_exam_preview_compat(exam_id):
    """Compatibility alias for preview pages."""
    return get_exam_questions(exam_id)
# ==========================================
# ROUTE: Get Exam Questions
# ==========================================
@app.route('/api/exam-questions/<exam_id>', methods=['GET'])
def get_exam_questions(exam_id):
    """Retrieve questions for an exam from Supabase"""
    try:
        user_ctx, auth_error = _optional_authenticated_user()
        if auth_error:
            return auth_error
        supabase = get_supabase()
        exam = _load_exam_row(supabase, exam_id, 'exam_id,id,teacher_id,status,is_visible_to_students,course_id')
        if not exam:
            return jsonify({
                'status': 'not_found',
                'exam_id': exam_id,
                'questions': [],
                'count': 0,
                'message': 'Exam not found'
            }), 404
        role = str((user_ctx or {}).get('role') or '').strip().lower()
        current_user_id = _user_ctx_profile_id(user_ctx) if user_ctx else None
        include_answer_key = False
        if role == 'teacher':
            owner = str(exam.get('teacher_id') or '').strip()
            if owner and owner == str(current_user_id):
                include_answer_key = True
            elif not _can_student_view_exam(exam):
                return jsonify({'status': 'forbidden', 'message': 'Exam is not available to this teacher', 'exam_id': exam_id}), 403
        elif role == 'admin':
            if str((user_ctx or {}).get('status') or '').strip().lower() != 'active':
                return jsonify({'status': 'forbidden', 'message': 'Active admin account required', 'exam_id': exam_id}), 403
            include_answer_key = True
        else:
            if not user_ctx or user_ctx.get('role') != 'student':
                return jsonify({'status': 'forbidden', 'message': 'Student authentication required', 'exam_id': exam_id}), 403
            if not _student_can_access_exam(supabase, user_ctx, exam):
                return jsonify({'status': 'forbidden', 'message': 'Exam is not available to students', 'exam_id': exam_id}), 403
       
        # Fetch questions sorted: MCQ first, then Short Answer, then Long Answer, then by question_order
        response = supabase.table('questions').select('*').eq('exam_id', exam_id).order('question_order').execute()

        if response and response.data:
            # Sort: MCQ → Short Answer → Long Answer, preserving order within each group
            TYPE_PRIORITY = {'mcq': 0, 'true_false': 1, 'short_answer': 2, 'long_answer': 3, 'essay': 4}
            def _type_sort_key(row):
                qt = str(row.get('question_type') or '').lower().replace(' ', '_').replace('-', '_')
                return (TYPE_PRIORITY.get(qt, 5), int(row.get('question_order') or 999))
            question_rows = sorted([dict(row or {}) for row in response.data], key=_type_sort_key)
            # ── Per-student question shuffling ────────────────────────
            import random as _random
            exam_full_for_shuffle = _load_exam_row(supabase, exam_id, 'exam_id,shuffle_questions')
            if (exam_full_for_shuffle or {}).get('shuffle_questions') and role == 'student':
                seed_str = str(current_user_id or '') + str(exam_id or '')
                _rng = _random.Random(hash(seed_str) % (2**32))
                _rng.shuffle(question_rows)
                for q in question_rows:
                    if isinstance(q.get('options'), dict) and len(q['options']) > 1:
                        items = list(q['options'].items())
                        _rng.shuffle(items)
                        q['options'] = dict(items)
            if not include_answer_key:
                question_rows = [_question_payload_for_candidate(row) for row in question_rows]
            return jsonify({
                'status': 'success',
                'exam_id': exam_id,
                'questions': question_rows,
                'count': len(question_rows)
            }), 200
        else:
            # Log debug info
            logger.warning("No questions found for exam_id: %s", exam_id)
            return jsonify({
                'status': 'not_found',
                'exam_id': exam_id,
                'questions': [],
                'count': 0,
                'message': 'No questions found for this exam'
            }), 404
           
    except Exception as e:
        logger.error("Error retrieving exam questions: %s", e)
        logger.debug("Exam ID format: %s", exam_id)
        return jsonify({
            'status': 'error',
            'message': str(e),
            'exam_id': exam_id
        }), 500
# ==========================================
# COMPAT ROUTE: Legacy submit endpoint
# ==========================================
@app.route('/api/submit-exam', methods=['POST'])
def submit_exam_compat():
    """
    Legacy compatibility endpoint.
    New flow stores answers/attempts directly in Supabase from frontend.
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('student')
        if auth_error:
            return auth_error
        payload = request.get_json(silent=True) or {}
        return jsonify({
            'success': True,
            'message': 'Legacy submit endpoint accepted (no-op).',
            'exam_id': payload.get('exam_id'),
            'attempt_id': payload.get('attempt_id')
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
# ==========================================
# ROUTE: Debug - List All Exams and Questions
# ==========================================
@app.route('/api/debug/db-status', methods=['GET'])
def db_status():
    """Debug endpoint to check database status"""
    try:
        state, identity, auth_error = _require_active_admin()
        if auth_error:
            return auth_error
        supabase = get_supabase()
       
        # Get all exams
        exams_resp = supabase.table('exams').select('*').limit(10).execute()
        exams = exams_resp.data if exams_resp.data else []
       
        # Get all questions
        questions_resp = supabase.table('questions').select('*').limit(20).execute()
        questions = questions_resp.data if questions_resp.data else []
       
        # Group questions by exam_id
        questions_by_exam = {}
        for q in questions:
            exam_id = q.get('exam_id')
            if exam_id not in questions_by_exam:
                questions_by_exam[exam_id] = 0
            questions_by_exam[exam_id] += 1
       
        # Analyze exams
        exam_ids = [e.get('exam_id') or e.get('id') for e in exams]
       
        return jsonify({
            'status': 'success',
            'exams': {
                'count': len(exams),
                'ids': exam_ids,
                'sample': exams[0] if exams else None
            },
            'questions': {
                'total_count': len(questions),
                'by_exam': questions_by_exam,
                'sample': questions[0] if questions else None
            }
        }), 200
       
    except Exception as e:
        logger.error("Error checking DB status: %s", e)
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
# ==========================================
# ROUTE: CodeBERT Analysis - Analyze Code Content
# ==========================================
@app.route('/api/codebert/analyze', methods=['POST'])
def analyze_code_with_codebert():
    """
    Analyze code using CodeBERT
   
    Request:
    {
        "code": "Python code here",
        "language": "python" (optional - auto-detected if not provided)
    }
   
    Response:
    {
        "success": true,
        "language": "Python",
        "concepts": {
            "functions": ["func1", "func2"],
            "classes": ["Class1"],
            "variables": ["var1"],
            "keywords": ["def", "if", "return"]
        },
        "model": "CodeBERT",
        "analysis_time": 0.23
    }
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        from models.question_generator import (
            detect_programming_language,
            extract_code_functions_and_concepts,
            analyze_code_with_codebert
        )
       
        data = request.json
        code = data.get('code', '')
        manual_language = data.get('language')
       
        if not code or len(code) < 10:
            return jsonify({
                'error': 'Code must be at least 10 characters'
            }), 400
       
        start_time = time.time()
       
        # Detect language
        language = manual_language or detect_programming_language(code)
       
        # Extract concepts
        concepts = extract_code_functions_and_concepts(code)
       
        # Analyze with CodeBERT
        codebert_analysis = analyze_code_with_codebert(code)
       
        analysis_time = time.time() - start_time
       
        return jsonify({
            'success': True,
            'language': language,
            'concepts': concepts,
            'codebert_analysis': bool(codebert_analysis),
            'model': 'CodeBERT',
            'analysis_time': round(analysis_time, 2)
        }), 200
       
    except Exception as e:
        logger.error("CodeBERT analysis error: %s", e)
        return jsonify({
            'error': str(e)
        }), 500
# ==========================================
# ROUTE: Generate Code-Focused Questions
# ==========================================
@app.route('/api/codebert/generate-code-questions', methods=['POST'])
def generate_code_questions():
    """
    Generate code-focused questions using CodeBERT
   
    Request:
    {
        "code": "Python/Java/C++ code here",
        "subject": "Algorithms", "Data Structures", etc.
        "num_questions": 5
    }
   
    Response:
    {
        "success": true,
        "language": "Python",
        "questions": [
            {
                "type": "MCQ",
                "text": "What does function X do?",
                "model": "CodeBERT",
                ...
            }
        ]
    }
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        from models.question_generator import (
            detect_programming_language,
            extract_code_functions_and_concepts
        )
       
        data = request.json
        code = data.get('code', '')
        subject = data.get('subject', 'Programming')
        num_questions = int(data.get('num_questions', 5))
       
        if not code or len(code) < 20:
            return jsonify({
                'error': 'Code must be at least 20 characters'
            }), 400
       
        if num_questions < 1 or num_questions > 20:
            return jsonify({
                'error': 'num_questions must be between 1 and 20'
            }), 400
       
        start_time = time.time()
       
        # Generate questions
        questions = generate_questions_from_text(
            text=code,
            subject=subject,
            num_questions=num_questions
        )
       
        # Detect language for metadata
        language = detect_programming_language(code)
       
        # Extract concepts
        concepts = extract_code_functions_and_concepts(code)
       
        generation_time = time.time() - start_time
       
        return jsonify({
            'success': True,
            'language': language,
            'questions': questions,
            'concepts': concepts,
            'count': len(questions),
            'generation_time': round(generation_time, 2),
            'model': 'CodeBERT + Ollama Qwen 2.5 7B'
        }), 200
       
    except Exception as e:
        logger.error("Code question generation error: %s", e)
        return jsonify({
            'error': str(e)
        }), 500
# ==========================================
# ROUTE: Check Model Status
# ==========================================
@app.route('/api/models/status', methods=['GET'])
def check_models_status():
    """
    Check if AI models are loaded and ready
    """
    try:
        from models.question_generator import MODELS_LOADED, get_generation_model_status
        runtime = get_generation_model_status()
        qwen_enabled = runtime.get('use_qwen_lora')
        qwen_ready = runtime.get('qwen_lora_adapter_present')
       
        # Check HF Space availability
        hf_space_url = os.getenv('HF_SPACE_URL', '').strip()
        hf_space_status = 'not_configured'
        if hf_space_url:
            try:
                import requests as _req
                r = _req.get(hf_space_url, timeout=5)
                hf_space_status = 'online' if r.status_code < 500 else 'error'
            except Exception:
                hf_space_status = 'offline'

        return jsonify({
            'success': True,
            'models': {
                'codebert': {
                    'name': 'microsoft/codebert-base',
                    'status': 'loaded' if MODELS_LOADED else 'loading',
                    'size_mb': 335,
                    'type': 'Code Understanding'
                },
                'ollama_qwen': {
                    'name': 'Ollama Qwen 2.5 7B (qwen2.5:7b-instruct-q5_K_M)',
                    'status': 'loaded' if runtime.get('ollama_available') else 'unavailable',
                    'size_mb': 5400,
                    'type': 'Question Generation (Ollama)'
                },
                'qwen_lora': {
                    'name': runtime.get('qwen_base_model'),
                    'status': (
                        'adapter_ready'
                        if qwen_enabled and qwen_ready
                        else ('disabled' if not qwen_enabled else 'adapter_missing')
                    ),
                    'adapter_path': runtime.get('qwen_lora_path'),
                    'pipeline_loaded': runtime.get('qwen_pipeline_loaded'),
                    'type': 'Question Generation (LoRA)'
                },
                'sentence_bert': {
                    'name': 'sentence-transformers/all-mpnet-base-v2',
                    'status': 'ready',
                    'size_mb': 438,
                    'type': 'Essay Grading'
                },
                'hf_space': {
                    'name': hf_space_url or 'Not configured',
                    'status': hf_space_status,
                    'type': 'Remote GPU (HF Space)',
                    'note': 'Falls back to local Ollama if unavailable'
                }
            },
            'overall_status': (
                'ready'
                if (qwen_enabled and qwen_ready) or MODELS_LOADED or runtime.get('ollama_available')
                else 'initializing'
            ),
            'message': (
                'Generation stack ready'
                if (qwen_enabled and qwen_ready) or MODELS_LOADED or runtime.get('ollama_available')
                else 'Models initializing on first use'
            ),
            'runtime': runtime
        }), 200
       
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500
# ==========================================
# ROUTE: Language Detection Info
# ==========================================
@app.route('/api/codebert/languages', methods=['GET'])
def get_supported_languages():
    """Get list of supported programming languages — public endpoint"""
    supported_languages = {
        'Python': 'Excellent support, primary focus',
        'Java': 'Full support, OOP patterns',
        'C': 'Strong support, pointer handling',
        'C++': 'Strong support, modern C++ features',
        'JavaScript': 'Full support, ES6+ syntax',
        'SQL': 'Query syntax, table operations',
        'HTML': 'Tag recognition',
        'CSS': 'Style rules and selectors'
    }
   
    return jsonify({
        'supported_languages': supported_languages,
        'model': 'CodeBERT',
        'total_languages': len(supported_languages)
    }), 200
# ==========================================
# ROUTE: Create Exam
# ==========================================
@app.route('/api/exams', methods=['POST'])
def create_exam():
    """
    Create a new exam record
   
    Request:
    {
        "teacher_id": "uuid",
        "course_id": "string",
        "title": "string",
        "subject": "string",
        "duration": int,
        "total_marks": int
    }
   
    Response:
    {
        "exam_id": "uuid",
        "message": "Exam created successfully"
    }
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        data = request.json or {}
        supabase = get_supabase()
       
        # Extract data
        teacher_id = _user_ctx_profile_id(user_ctx)
        course_id = data.get('course_id')
        title = data.get('title', 'Untitled Exam')
        subject = data.get('subject', 'General')
        duration = data.get('duration', 90)
        total_marks = data.get('total_marks', 100)
        if data.get('teacher_id') and str(data.get('teacher_id')) != str(teacher_id):
            return jsonify({'error': 'Forbidden: teacher identity mismatch'}), 403
        course_row, course_error = _require_teacher_course_owner(supabase, course_id, user_ctx)
        if course_error:
            return course_error
       
        if not teacher_id:
            return jsonify({'error': 'teacher_id is required'}), 400
       
        logger.info("Creating exam: %s for teacher: %s", title, teacher_id)
       
        # Create exam in Supabase
        exam_data = {
            'teacher_id': teacher_id,
            'exam_title': title,
            'title': title,
            'subject': subject,
            'duration_minutes': duration,
            'total_marks': total_marks,
            'status': 'draft',
            'is_visible_to_students': False,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        # Add optional fields gracefully (columns may not exist yet)
        try:
            exam_data['max_attempts'] = int(data.get('max_attempts') or 1)
        except Exception:
            pass
        if data.get('exam_start_time'):
            t = str(data.get('exam_start_time')).strip()
            # If full datetime (YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS), extract time part only
            if 'T' in t:
                t = t.split('T')[1]
            exam_data['exam_start_time'] = t if len(t) >= 8 else t + ':00'
        if data.get('exam_end_time'):
            t = str(data.get('exam_end_time')).strip()
            if 'T' in t:
                t = t.split('T')[1]
            exam_data['exam_end_time'] = t if len(t) >= 8 else t + ':00'
        exam_data['course_id'] = str(course_row.get('id') or course_id)
       
        try:
            result = db_exec(lambda: supabase.table('exams').insert(exam_data).execute())
            if not result.data:
                return jsonify({'error': 'Failed to create exam in database'}), 500
            exam_id = result.data[0].get('exam_id') or result.data[0].get('id')
            logger.info("Exam created with ID: %s", exam_id)
        except Exception as e:
            logger.error("Database insert failed while creating exam: %s", e)
            return jsonify({
                'error': 'Failed to create exam in database',
                'details': str(e)
            }), 500

        return jsonify({
            'exam_id': exam_id,
            'message': 'Exam created successfully'
        }), 201
       
    except Exception as e:
        logger.error("Error creating exam: %s", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
# ==========================================
# ROUTE: Create Exam With Questions (Publish)
# ==========================================
@app.route('/api/exams/create', methods=['POST'])
def create_exam_with_questions():
    """
    Create a new exam with questions in a single request.
    Expected payload from exam-preview.html.
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        data = request.json or {}
        supabase = get_supabase()
        title = data.get('title', 'Untitled Exam')
        duration = data.get('duration', 90)
        questions = data.get('questions', [])
        subject = data.get('subject', 'General')
        course_id = data.get('course_id') or data.get('courseId')
        teacher_id = _user_ctx_profile_id(user_ctx)
        supplied_teacher_id = data.get('teacher_id') or data.get('teacherId')
        if supplied_teacher_id and str(supplied_teacher_id) != str(teacher_id):
            return jsonify({'error': 'Forbidden: teacher identity mismatch'}), 403
        course_row, course_error = _require_teacher_course_owner(supabase, course_id, user_ctx)
        if course_error:
            return course_error
        if not questions:
            return jsonify({'error': 'No questions provided'}), 400
        total_marks = data.get('totalMarks') or data.get('total_marks')
        if total_marks is None:
            total_marks = sum((q.get('marks') or 1) for q in questions)
        exam_data = {
            'teacher_id': teacher_id,
            'exam_title': title,
            'title': title,
            'subject': subject,
            'duration_minutes': duration,
            'total_marks': total_marks,
            'total_questions': len(questions),
            'status': 'published',
            'is_visible_to_students': True,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        exam_data['course_id'] = str(course_row.get('id') or course_id)
        exam_result = db_exec(lambda: supabase.table('exams').insert(exam_data).execute())
        if not exam_result.data:
            return jsonify({'error': 'Failed to create exam'}), 500
        exam_id = exam_result.data[0].get('exam_id') or exam_result.data[0].get('id')
        saved = 0
        for idx, q in enumerate(questions):
            question_text = (
                q.get('question_text') or q.get('question') or q.get('text') or q.get('prompt')
            )
            if not question_text:
                continue
            question_data = {
                'exam_id': exam_id,
                'question_text': question_text,
                'question_type': to_db_question_type(q.get('question_type') or q.get('type')),
                'difficulty': q.get('difficulty', 'medium'),
                'marks': q.get('marks') or q.get('points') or 1,
                'options': q.get('options') or q.get('choices'),
                'correct_answer': q.get('correct_answer') or q.get('answer') or q.get('correct'),
                'explanation': q.get('explanation'),
                'ai_generated': q.get('ai_generated', True),
                'topic': q.get('topic', subject),
                'question_order': idx + 1
            }
            inserted = False
            last_err = None
            for qt in build_question_type_candidates(q.get('question_type') or q.get('type')):
                try:
                    question_data['question_type'] = qt
                    if not is_objective_type(qt):
                        question_data['options'] = None
                        question_data['correct_answer'] = None
                    result = db_exec(lambda: supabase.table('questions').insert(question_data).execute())
                    if result.data:
                        saved += 1
                        inserted = True
                        break
                except Exception as ie:
                    last_err = ie
                    continue
            if not inserted and last_err:
                raise last_err
        return jsonify({
            'success': True,
            'exam_id': exam_id,
            'questions_saved': saved,
            'message': 'Exam published successfully'
        }), 200
    except Exception as e:
        logger.error("Error publishing exam: %s", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
@app.route('/api/exams/<exam_id>/questions', methods=['PUT'])
def replace_exam_questions(exam_id):
    """
    Replace all questions of an existing exam.
    Used by question-editor/exam-preview flow to persist teacher edits before publish.
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        data = request.json or {}
        questions = data.get('questions') or []
        teacher_id = _user_ctx_profile_id(user_ctx)
        supplied_teacher_id = data.get('teacher_id') or data.get('teacherId')
        supabase = get_supabase()
        if not isinstance(questions, list) or len(questions) == 0:
            return jsonify({'error': 'questions array is required'}), 400
        if supplied_teacher_id and str(supplied_teacher_id) != str(teacher_id):
            return jsonify({'error': 'Forbidden: teacher identity mismatch'}), 403
        _, exam_auth_error = _require_teacher_exam_owner(supabase, exam_id, user_ctx)
        if exam_auth_error:
            return exam_auth_error
        # Remove existing questions first
        try:
            db_exec(lambda: supabase.table('questions').delete().eq('exam_id', exam_id).execute())
        except Exception as e:
            logger.warning("Unable to delete existing questions for exam %s: %s", exam_id, e)
        saved = 0
        save_errors = []
        total_marks = 0
        subject = data.get('subject', 'General')
        for idx, q in enumerate(questions):
            question_text = _sanitize_text(q.get('question_text') or q.get('question') or q.get('text') or q.get('prompt') or '')
            if not question_text:
                question_text = f"Generated question {idx + 1}"
            marks = _safe_int(q.get('marks') or q.get('points') or 1, 1)
            total_marks += marks
            raw_options = q.get('options') or q.get('choices')
            options = _sanitize_jsonish(raw_options)
            # If frontend sends options as array [{text,is_correct}], convert to object {A: text, ...}
            if isinstance(raw_options, list):
                letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                options = {}
                correct = q.get('correct_answer')
                for i, opt in enumerate(raw_options):
                    key = letters[i] if i < len(letters) else str(i + 1)
                    text = _sanitize_text(opt.get('text') if isinstance(opt, dict) else str(opt or ''))
                    options[key] = text
                    if not correct and isinstance(opt, dict) and bool(opt.get('is_correct')):
                        correct = key
                q['correct_answer'] = correct
            question_data = {
                'exam_id': exam_id,
                'question_text': question_text,
                'question_type': to_db_question_type(q.get('question_type') or q.get('type')),
                'difficulty': q.get('difficulty', 'medium'),
                'marks': marks,
                'options': options,
                'correct_answer': _sanitize_text(q.get('correct_answer') or q.get('answer') or q.get('correct')),
                'explanation': _sanitize_text(q.get('explanation')),
                'ai_generated': q.get('ai_generated', True),
                'topic': _sanitize_text(q.get('topic', subject)),
                'question_order': idx + 1
            }
            inserted = False
            last_err = None
            for qt in build_question_type_candidates(q.get('question_type') or q.get('type')):
                try:
                    question_data['question_type'] = qt
                    if not is_objective_type(qt):
                        question_data['options'] = None
                        question_data['correct_answer'] = None
                    else:
                        if not isinstance(question_data.get('options'), dict) or len(question_data['options']) < 2:
                            question_data['options'] = {'A': 'True', 'B': 'False'}
                        if not question_data.get('correct_answer'):
                            question_data['correct_answer'] = 'A'
                    result = db_exec(lambda: supabase.table('questions').insert(question_data).execute())
                    if result.data:
                        saved += 1
                        inserted = True
                        break
                except Exception as ie:
                    last_err = ie
                    continue
            if not inserted:
                # Final fallback row so question count doesn't silently shrink.
                try:
                    fallback_row = {
                        'exam_id': exam_id,
                        'question_text': question_text or f"Generated question {idx + 1}",
                        'question_type': 'long_answer',
                        'difficulty': 'medium',
                        'marks': marks,
                        'options': None,
                        'correct_answer': None,
                        'explanation': None,
                        'ai_generated': q.get('ai_generated', True),
                        'topic': _sanitize_text(subject),
                        'question_order': idx + 1
                    }
                    result = db_exec(lambda: supabase.table('questions').insert(fallback_row).execute())
                    if result.data:
                        saved += 1
                        inserted = True
                except Exception as fallback_err:
                    save_errors.append(f"q{idx+1}: {fallback_err}")
                    if last_err:
                        save_errors.append(f"q{idx+1}-orig: {last_err}")
        # Keep exam counters synced with replaced set
        try:
            db_exec(lambda: supabase.table('exams').update({
                'total_questions': saved,
                'total_marks': total_marks,
                'updated_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }).eq('exam_id', exam_id).execute())
        except Exception:
            try:
                db_exec(lambda: supabase.table('exams').update({
                    'total_questions': saved,
                    'total_marks': total_marks,
                    'updated_at': time.strftime('%Y-%m-%d %H:%M:%S')
                }).eq('id', exam_id).execute())
            except Exception as e:
                logger.warning("Could not sync exam totals for %s: %s", exam_id, e)
        return jsonify({
            'success': True,
            'exam_id': exam_id,
            'questions_saved': saved,
            'total_marks': total_marks,
            'warnings': save_errors[:6]
        }), 200
    except Exception as e:
        logger.error("Error replacing exam questions: %s", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# Direct endpoint for student exam listing (bypassing blueprint routing issues)
@app.route('/api/exams', methods=['GET'])
def list_exams_root():
    """
    List exams for students (GET /api/exams)
    Supports both Bearer JWT token and X-User-* headers.
    """
    try:
        supabase = get_supabase()

        # ── Resolve user identity ──────────────────────────────
        # Check X-User-* headers first (fast path, used by test scripts and RBAC)
        user_id   = request.headers.get('X-User-ID', '').strip()
        user_role = (request.headers.get('X-User-Role') or '').strip().lower()

        # Try Bearer JWT if headers not present
        if not user_id:
            bearer = _bearer_token()
            if bearer:
                try:
                    auth_resp  = supabase.auth.get_user(bearer)
                    auth_user  = getattr(auth_resp, 'user', None)
                    auth_email = str(getattr(auth_user, 'email', '') or '').strip().lower()
                    auth_uid   = str(getattr(auth_user, 'id',    '') or '').strip()
                    if auth_email:
                        profile = _load_user_profile_for_auth(supabase, auth_email, auth_uid)
                        user_id   = _user_ctx_profile_id({'auth_id': auth_uid, 'profile': profile})
                        if not user_role:
                            user_role = str(profile.get('role') or '').strip().lower()
                except Exception:
                    pass

        if not user_id or not user_role:
            return jsonify({'success': False, 'error': 'Authentication required', 'exams': [], 'count': 0}), 401

        # ── Student: return published exams for enrolled courses ──
        if user_role == 'student':
            course_ids = set()

            # Primary: enrollments table
            try:
                enroll_r = supabase.table('enrollments').select('course_id,status').eq('student_id', user_id).execute()
                for row in (enroll_r.data or []):
                    if str(row.get('status') or '').lower() == 'active' and row.get('course_id'):
                        course_ids.add(row['course_id'])
            except Exception:
                pass

            # Fallback: course_enrollments table
            if not course_ids:
                try:
                    ce_r = supabase.table('course_enrollments').select('course_code').eq('user_id', user_id).eq('enrollment_status', 'active').execute()
                    codes = [e['course_code'] for e in (ce_r.data or []) if e.get('course_code')]
                    if codes:
                        cr = supabase.table('courses').select('id').in_('course_code', codes).execute()
                        for c in (cr.data or []):
                            if c.get('id'):
                                course_ids.add(c['id'])
                except Exception:
                    pass

            if not course_ids:
                return jsonify({'success': True, 'exams': [], 'count': 0}), 200

            exams_result = supabase.table('exams').select('*').in_('course_id', list(course_ids)).eq('status', 'published').execute()
            exams = exams_result.data or []
            return jsonify({'success': True, 'exams': exams, 'count': len(exams)}), 200

        # ── Other roles: delegate to list_exams ──────────────────
        return list_exams()

    except Exception as e:
        logger.error("list_exams_root error: %s", e)
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'exams': [], 'count': 0}), 500

# ==========================================
# ROUTE: Update Exam (Publish/Edit)
# ==========================================
@app.route('/api/exams/<exam_id>', methods=['PUT'])
def update_exam(exam_id):
    """
    Update an existing exam by exam_id (or id fallback).
    Used by create-exam publish flow to avoid creating duplicate exams.
    """
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        data = request.json or {}
        supabase = get_supabase()
        requester_teacher_id = _user_ctx_profile_id(user_ctx)
        supplied_teacher_id = (
            data.get('teacher_id')
            or request.args.get('teacher_id')
            or request.headers.get('X-Teacher-Id')
            or request.headers.get('X-User-Id')
        )
        if supplied_teacher_id and str(supplied_teacher_id) != str(requester_teacher_id):
            return jsonify({'error': 'Forbidden: teacher identity mismatch'}), 403
        exam_row, exam_auth_error = _require_teacher_exam_owner(supabase, exam_id, user_ctx)
        if exam_auth_error:
            return exam_auth_error
        update_data = {}
        effective_course_row = None
        if 'course_id' in data:
            course_row, course_error = _require_teacher_course_owner(supabase, data.get('course_id'), user_ctx)
            if course_error:
                return course_error
            effective_course_row = course_row
            update_data['course_id'] = str(course_row.get('id') or data.get('course_id'))
        if 'status' in data:
            raw_status = str(data.get('status') or '').strip().lower()
            # Canonical exam statuses:
            # draft -> hidden from students
            # published -> visible/available to students
            # archived -> closed/finished
            status_aliases = {
                'active': 'published',
                'closed': 'archived',
                'inactive': 'archived',
                'completed': 'archived',
                'unpublished': 'draft'
            }
            normalized_status = status_aliases.get(raw_status, raw_status)
            allowed_statuses = {'draft', 'published', 'archived'}
            if normalized_status and normalized_status not in allowed_statuses:
                return jsonify({
                    'error': f'Invalid status "{raw_status}"',
                    'allowed_statuses': sorted(list(allowed_statuses))
                }), 400
            if normalized_status:
                update_data['status'] = normalized_status
            if normalized_status == 'published':
                effective_course_id = str(update_data.get('course_id') or exam_row.get('course_id') or '').strip()
                if not effective_course_id:
                    return jsonify({'error': 'A valid course must be selected before publishing an exam'}), 400
                if not effective_course_row:
                    effective_course_row, course_error = _require_teacher_course_owner(supabase, effective_course_id, user_ctx)
                    if course_error:
                        return course_error
                    update_data['course_id'] = str(effective_course_row.get('id') or effective_course_id)
                update_data['published_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
                update_data['is_visible_to_students'] = True
            elif normalized_status == 'draft':
                update_data['is_visible_to_students'] = False
        if 'scheduled_at' in data:
            update_data['scheduled_at'] = data.get('scheduled_at')
        if 'instructions' in data:
            update_data['instructions'] = data.get('instructions')
        if 'duration' in data:
            update_data['duration_minutes'] = data.get('duration')
        if 'total_marks' in data:
            update_data['total_marks'] = data.get('total_marks')
        if 'title' in data and data.get('title'):
            update_data['title'] = data.get('title')
            update_data['exam_title'] = data.get('title')
        if 'max_attempts' in data:
            try:
                update_data['max_attempts'] = max(1, int(data.get('max_attempts') or 1))
            except Exception:
                pass
        if 'exam_start_time' in data:
            t = str(data.get('exam_start_time') or '').strip()
            if t and 'T' in t:
                t = t.split('T')[1]
            update_data['exam_start_time'] = (t if len(t) >= 8 else t + ':00') if t else None
        if 'exam_end_time' in data:
            t = str(data.get('exam_end_time') or '').strip()
            if t and 'T' in t:
                t = t.split('T')[1]
            update_data['exam_end_time'] = (t if len(t) >= 8 else t + ':00') if t else None
        if not update_data:
            return jsonify({'error': 'No fields to update'}), 400
        update_data['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        # 1) Try update by exam_id column
        result = db_exec(lambda: supabase.table('exams').update(update_data).eq('exam_id', exam_id).execute())
        if result.data and len(result.data) > 0:
            updated = result.data[0]
            # ── Email: notify students when exam is published ──────────
            if normalized_status == 'published':
                try:
                    from utils.email_notify import notify_exam_published
                    course_id_for_email = str(updated.get('course_id') or '').strip()
                    exam_title_for_email = str(updated.get('exam_title') or updated.get('title') or 'Exam')
                    course_name_for_email = ''
                    if course_id_for_email:
                        cr = db_exec(lambda: supabase.table('courses').select('course_name').eq('id', course_id_for_email).limit(1).execute())
                        course_name_for_email = (cr.data[0].get('course_name') or '') if cr.data else ''
                        enroll_r = db_exec(lambda: supabase.table('enrollments').select('student_id').eq('course_id', course_id_for_email).eq('status', 'active').execute())
                        student_ids = [r.get('student_id') for r in (enroll_r.data or []) if r.get('student_id')]
                        if student_ids:
                            users_r = db_exec(lambda: supabase.table('users').select('email').in_('id', student_ids).eq('status', 'active').execute())
                            emails = [u.get('email') for u in (users_r.data or []) if u.get('email')]
                            import threading
                            threading.Thread(
                                target=notify_exam_published,
                                args=(emails, exam_title_for_email, course_name_for_email),
                                daemon=True
                            ).start()
                except Exception as email_err:
                    logger.warning("[email] Exam publish notification failed: %s", email_err)
            return jsonify({
                'success': True,
                'exam_id': updated.get('exam_id') or updated.get('id'),
                'message': 'Exam updated successfully'
            }), 200
        # 2) Fallback update by id column
        result = db_exec(lambda: supabase.table('exams').update(update_data).eq('id', exam_id).execute())
        if result.data and len(result.data) > 0:
            updated = result.data[0]
            return jsonify({
                'success': True,
                'exam_id': updated.get('exam_id') or updated.get('id'),
                'message': 'Exam updated successfully'
            }), 200
        return jsonify({'error': 'Exam not found'}), 404
    except Exception as e:
        logger.error("Error updating exam: %s", e)
        return jsonify({'error': str(e)}), 500
# ==========================================
# ROUTE: List Exams
# ==========================================
@app.route('/api/exams/list', methods=['GET'])
def list_exams():
    """
    List exams for students/teachers
    Optional query params:
        status: comma-separated statuses (default: published,draft,archived)
        teacher_id: filter by teacher UUID
        course_id: filter by course UUID
        limit: max results (default: 50)
    """
    try:
        user_ctx, auth_error = _optional_authenticated_user()
        if auth_error:
            return auth_error
        supabase = get_supabase()
        status_param = request.args.get('status', 'published,draft,archived')
        status_aliases = {
            'active': 'published',
            'closed': 'archived',
            'inactive': 'archived',
            'completed': 'archived'
        }
        statuses = []
        for s in [x.strip() for x in status_param.split(',') if x.strip()]:
            statuses.append(status_aliases.get(s.lower(), s.lower()))
        teacher_id = request.args.get('teacher_id')
        course_id = request.args.get('course_id')
        role = str((user_ctx or {}).get('role') or '').strip().lower()
        current_user_id = _user_ctx_profile_id(user_ctx) if user_ctx else None
        limit = request.args.get('limit', '50')
        try:
            limit_val = max(1, min(int(limit), 200))
        except Exception:
            limit_val = 50
        query = supabase.table('exams').select('*')
        if role == 'teacher':
            if str((user_ctx or {}).get('status') or '').strip().lower() != 'active':
                return jsonify({'error': 'Active account required'}), 403
            if teacher_id and str(teacher_id) != str(current_user_id):
                return jsonify({'error': 'Forbidden: teacher filter does not match authenticated user'}), 403
            if statuses:
                query = query.in_('status', statuses)
            query = query.eq('teacher_id', current_user_id)
        elif role == 'admin':
            if str((user_ctx or {}).get('status') or '').strip().lower() != 'active':
                return jsonify({'error': 'Active admin account required'}), 403
            if statuses:
                query = query.in_('status', statuses)
            if teacher_id:
                query = query.eq('teacher_id', teacher_id)
        elif role == 'student':
            if str((user_ctx or {}).get('status') or '').strip().lower() != 'active':
                return jsonify({'error': 'Active student account required'}), 403
            enrolled_course_ids = _load_student_course_ids(supabase, current_user_id)
            if course_id:
                normalized_course_id = str(course_id).strip()
                if normalized_course_id not in enrolled_course_ids:
                    return jsonify({'success': True, 'count': 0, 'exams': []}), 200
                enrolled_course_ids = {normalized_course_id}
            if not enrolled_course_ids:
                return jsonify({'success': True, 'count': 0, 'exams': []}), 200
            query = query.in_('status', ['published']).eq('is_visible_to_students', True).in_('course_id', list(enrolled_course_ids))
        else:
            return jsonify({'success': True, 'count': 0, 'exams': []}), 200
        if course_id and role in ('teacher', 'admin'):
            query = query.eq('course_id', course_id)
        result = query.order('created_at', desc=True).limit(limit_val).execute()
        exams = result.data if result.data else []
        if role == 'student':
            exams = [exam for exam in exams if _student_matches_exam_scope(user_ctx, exam)]
        course_ids = sorted({
            str(exam.get('course_id') or '').strip()
            for exam in exams
            if exam.get('course_id')
        })
        course_map = {}
        if course_ids:
            course_resp = db_exec(
                lambda: supabase.table('courses')
                .select('id,course_code,course_name,semester,academic_year')
                .in_('id', course_ids)
                .execute()
            )
            course_map = {
                str(row.get('id') or '').strip(): dict(row or {})
                for row in (course_resp.data or [])
                if row.get('id')
            }
        # Student view should only include exams aligned to the assigned course owner.
        if role == 'student' and course_map:
            filtered = []
            for exam in exams:
                course_id_value = str(exam.get('course_id') or '').strip()
                course_row = course_map.get(course_id_value)
                if not course_row:
                    continue
                course_teacher = str(course_row.get('teacher_id') or '').strip()
                exam_teacher = str(exam.get('teacher_id') or '').strip()
                if course_teacher and exam_teacher and course_teacher != exam_teacher:
                    continue
                if course_teacher and not exam_teacher:
                    continue
                filtered.append(exam)
            exams = filtered
        enriched_exams = []
        for exam in exams:
            exam_payload = dict(exam or {})
            course_row = course_map.get(str(exam_payload.get('course_id') or '').strip())
            if course_row:
                exam_payload.setdefault('course_code', course_row.get('course_code'))
                exam_payload.setdefault('course_name', course_row.get('course_name'))
                # semester field will be added in future database migration
                # exam_payload.setdefault('semester', course_row.get('semester'))
                exam_payload.setdefault('academic_year', course_row.get('academic_year'))
            enriched_exams.append(exam_payload)
        return jsonify({
            'success': True,
            'count': len(enriched_exams),
            'exams': enriched_exams
        }), 200
    except Exception as e:
        logger.error("Error listing exams: %s", e)
        return jsonify({'error': str(e)}), 500
@app.route('/api/student/courses', methods=['GET'])
def student_list_courses():
    try:
        user_ctx, auth_error = _require_authenticated_roles('student')
        if auth_error:
            return auth_error
        if str((user_ctx or {}).get('status') or '').strip().lower() != 'active':
            return jsonify({'success': False, 'error': 'Active student account required', 'courses': []}), 403
        supabase = get_supabase()
        student_id = _user_ctx_profile_id(user_ctx)
        enrollments = _load_student_enrollments(supabase, student_id)
        course_ids = [str(row.get('course_id') or '').strip() for row in enrollments if row.get('course_id')]
        if not course_ids:
            return jsonify({'success': True, 'count': 0, 'courses': []}), 200

        course_resp = db_exec(
            lambda: supabase.table('courses')
            .select('id,course_code,course_name,semester,academic_year,teacher_id')
            .in_('id', course_ids)
            .execute()
        )
        courses_by_id = {
            str((row.get('id') or row.get('course_id') or '')).strip(): dict(row or {})
            for row in (course_resp.data or [])
        }
        courses = []
        for course_id in course_ids:
            course_row = courses_by_id.get(course_id)
            if course_row:
                courses.append(_serialize_course_summary(course_row))

        return jsonify({'success': True, 'count': len(courses), 'courses': courses}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'courses': []}), 500


@app.route('/api/teacher/courses', methods=['GET'])
def teacher_list_courses():
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error
        if str((user_ctx or {}).get('status') or '').strip().lower() != 'active':
            return jsonify({'success': False, 'error': 'Active teacher account required', 'courses': []}), 403

        supabase = get_supabase()
        profile = (user_ctx or {}).get('profile') or {}
        teacher_id = _user_ctx_profile_id(user_ctx)
        teacher_alt_id = str(profile.get('teacher_id') or '').strip()
        teacher_ids = [str(teacher_id or '').strip(), teacher_alt_id, str(user_ctx.get('auth_id') or '').strip()]
        teacher_ids = [tid for tid in teacher_ids if tid]
        if not teacher_ids:
            return jsonify({'success': False, 'error': 'Teacher profile id is missing', 'courses': []}), 400

        uuid_ids = [tid for tid in teacher_ids if _is_valid_uuid(tid)]
        raw_ids = [tid for tid in teacher_ids if not _is_valid_uuid(tid)]
        seen = {}
        teacher_email = str(user_ctx.get('email') or '').strip().lower()

        def _merge_courses(rows):
            for row in (rows or []):
                course_payload = _serialize_course_summary(row)
                course_payload['subject'] = row.get('subject')
                course_id = str(course_payload.get('id') or course_payload.get('course_id') or '').strip()
                if course_id and course_id in seen:
                    continue
                seen[course_id or f"row-{len(seen)+1}"] = course_payload

        def _matches_teacher(row):
            if not row:
                return False
            for key in ('teacher_id', 'teacherId', 'teacher', 'instructor_id', 'instructorId', 'owner_id', 'ownerId'):
                value = str(row.get(key) or '').strip()
                if value and value in teacher_ids:
                    return True
            for key in ('teacher_email', 'teacherEmail', 'instructor_email', 'owner_email', 'email'):
                value = str(row.get(key) or '').strip().lower()
                if value and teacher_email and value == teacher_email:
                    return True
            return False

        if uuid_ids:
            try:
                resp = db_exec(
                    lambda: supabase.table('courses')
                    .select('id,course_code,course_name,semester,academic_year,teacher_id,subject')
                    .in_('teacher_id', uuid_ids)
                    .order('course_code')
                    .limit(500)
                    .execute()
                )
            except Exception as exc:
                if _is_missing_column_error(exc):
                    resp = db_exec(
                        lambda: supabase.table('courses')
                        .select('id,course_code,course_name,semester,academic_year,teacher_id')
                        .in_('teacher_id', uuid_ids)
                        .order('course_code')
                        .limit(500)
                        .execute()
                    )
                else:
                    raise
            _merge_courses(resp.data)

        if raw_ids:
            try:
                try:
                    resp = db_exec(
                        lambda: supabase.table('courses')
                        .select('id,course_code,course_name,semester,academic_year,teacher_id,subject')
                        .in_('teacher_id', raw_ids)
                        .order('course_code')
                        .limit(500)
                        .execute()
                    )
                except Exception as exc:
                    if _is_missing_column_error(exc):
                        resp = db_exec(
                            lambda: supabase.table('courses')
                            .select('id,course_code,course_name,semester,academic_year,teacher_id')
                            .in_('teacher_id', raw_ids)
                            .order('course_code')
                            .limit(500)
                            .execute()
                        )
                    else:
                        raise
                _merge_courses(resp.data)
            except Exception as raw_err:
                if 'invalid input syntax for type uuid' not in str(raw_err or '').lower():
                    raise

        if not seen:
            try:
                fallback = db_exec(
                    lambda: supabase.table('courses')
                    .select('*')
                    .order('course_code')
                    .limit(500)
                    .execute()
                )
                for row in (fallback.data or []):
                    if _matches_teacher(row):
                        _merge_courses([row])
            except Exception as fallback_err:
                if _is_missing_column_error(fallback_err):
                    pass
                else:
                    raise

        courses = list(seen.values())

        return jsonify({'success': True, 'count': len(courses), 'courses': courses}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'courses': []}), 500


@app.route('/api/teacher/students', methods=['GET'])
def teacher_enrolled_students():
    """Get all students enrolled in this teacher's courses."""
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher')
        if auth_error:
            return auth_error

        supabase = get_supabase()
        teacher_id = _user_ctx_profile_id(user_ctx)

        # Get teacher's courses
        courses_resp = db_exec(lambda: supabase.table('courses')
            .select('id,course_code,course_name')
            .eq('teacher_id', teacher_id)
            .execute())
        courses = courses_resp.data or []

        if not courses:
            return jsonify({'success': True, 'students': [], 'courses': [], 'count': 0}), 200

        course_ids = [c['id'] for c in courses if c.get('id')]
        course_map = {c['id']: f"{c.get('course_code','')} - {c.get('course_name','')}" for c in courses}

        # Get enrollments
        enr_resp = db_exec(lambda: supabase.table('enrollments')
            .select('student_id,course_id,status')
            .in_('course_id', course_ids)
            .execute())
        enrollments = enr_resp.data or []

        # Get unique student IDs
        student_ids = list(set(e['student_id'] for e in enrollments if e.get('student_id')))

        if not student_ids:
            return jsonify({'success': True, 'students': [], 'courses': courses, 'count': 0}), 200

        # Get student profiles
        students_resp = db_exec(lambda: supabase.table('users')
            .select('id,first_name,last_name,email,student_id,status,department,batch')
            .in_('id', student_ids)
            .execute())
        students_data = students_resp.data or []

        # Build student → courses map
        student_courses = {}
        for e in enrollments:
            sid = e.get('student_id')
            cid = e.get('course_id')
            if sid and cid:
                if sid not in student_courses:
                    student_courses[sid] = []
                label = course_map.get(cid, cid)
                if label not in student_courses[sid]:
                    student_courses[sid].append(label)

        # Build response
        result = []
        for s in students_data:
            sid = s.get('id', '')
            result.append({
                'id': sid,
                'first_name': s.get('first_name', ''),
                'last_name': s.get('last_name', ''),
                'full_name': f"{s.get('first_name','')} {s.get('last_name','')}".strip() or s.get('email',''),
                'email': s.get('email', ''),
                'student_id': s.get('student_id', ''),
                'status': s.get('status', 'active'),
                'department': s.get('department', ''),
                'batch': s.get('batch', ''),
                'enrolled_courses': student_courses.get(sid, []),
            })

        return jsonify({'success': True, 'students': result, 'courses': courses, 'count': len(result)}), 200
    except Exception as e:
        logger.error('[teacher/students] Error: %s', e)
        return jsonify({'success': False, 'error': str(e), 'students': []}), 500


# ==========================================
# ROUTE: Student Performance Trend
# ==========================================
@app.route('/api/student/performance', methods=['GET'])
def student_performance():
    """Get a student's score trend across all their exam attempts."""
    try:
        user_ctx, auth_error = _require_authenticated_roles('student', 'teacher', 'admin')
        if auth_error:
            return auth_error

        supabase = get_supabase()
        student_id = _user_ctx_profile_id(user_ctx)

        # Teachers/admins can query any student via ?student_id=
        target_id = request.args.get('student_id') or student_id
        if user_ctx.get('role') == 'student':
            target_id = student_id  # students can only see their own

        # Get all completed attempts with scores
        attempts_resp = db_exec(lambda: supabase.table('exam_attempts')
            .select('attempt_id,exam_id,score,total_marks,percentage,submitted_at,status')
            .eq('student_id', target_id)
            .in_('status', ['graded', 'completed', 'submitted', 'pending_grading'])
            .order('submitted_at', desc=False)
            .limit(50)
            .execute())
        attempts = attempts_resp.data or []

        if not attempts:
            return jsonify({'success': True, 'trend': [], 'stats': {
                'total_attempts': 0, 'avg_score': 0, 'best_score': 0, 'latest_score': 0
            }}), 200

        # Enrich with exam titles
        exam_ids = list({a['exam_id'] for a in attempts if a.get('exam_id')})
        exam_map = {}
        if exam_ids:
            exams_resp = db_exec(lambda: supabase.table('exams')
                .select('exam_id,exam_title,subject')
                .in_('exam_id', exam_ids)
                .execute())
            for e in (exams_resp.data or []):
                exam_map[e['exam_id']] = e

        trend = []
        for a in attempts:
            pct = a.get('percentage')
            if pct is None and a.get('total_marks') and float(a.get('total_marks', 0)) > 0:
                pct = round(float(a.get('score', 0)) / float(a['total_marks']) * 100, 1)
            exam_info = exam_map.get(a.get('exam_id'), {})
            trend.append({
                'attempt_id': a.get('attempt_id'),
                'exam_id': a.get('exam_id'),
                'exam_title': exam_info.get('exam_title', 'Exam'),
                'subject': exam_info.get('subject', ''),
                'score': a.get('score', 0),
                'total_marks': a.get('total_marks', 0),
                'percentage': round(float(pct), 1) if pct is not None else None,
                'submitted_at': a.get('submitted_at'),
                'status': a.get('status'),
            })

        percentages = [t['percentage'] for t in trend if t['percentage'] is not None]
        stats = {
            'total_attempts': len(trend),
            'avg_score': round(sum(percentages) / len(percentages), 1) if percentages else 0,
            'best_score': max(percentages) if percentages else 0,
            'latest_score': percentages[-1] if percentages else 0,
            'improvement': round(percentages[-1] - percentages[0], 1) if len(percentages) >= 2 else 0,
        }
        return jsonify({'success': True, 'trend': trend, 'stats': stats}), 200
    except Exception as e:
        logger.error('[student/performance] Error: %s', e)
        return jsonify({'success': False, 'error': str(e), 'trend': []}), 500


# ==========================================
# ROUTE: Exam Leaderboard
# ==========================================
@app.route('/api/exams/<exam_id>/leaderboard', methods=['GET'])
def exam_leaderboard(exam_id):
    """Get top students for an exam (teacher/admin only)."""
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher', 'admin')
        if auth_error:
            return auth_error

        supabase = get_supabase()
        limit = min(int(request.args.get('limit', 10)), 50)

        # Get all graded attempts for this exam
        attempts_resp = db_exec(lambda: supabase.table('exam_attempts')
            .select('attempt_id,student_id,score,total_marks,percentage,submitted_at,status')
            .eq('exam_id', exam_id)
            .in_('status', ['graded', 'completed', 'submitted', 'pending_grading'])
            .execute())
        attempts = attempts_resp.data or []

        if not attempts:
            return jsonify({'success': True, 'leaderboard': [], 'exam_id': exam_id, 'total': 0}), 200

        # Get student profiles
        student_ids = list({a['student_id'] for a in attempts if a.get('student_id')})
        student_map = {}
        if student_ids:
            students_resp = db_exec(lambda: supabase.table('users')
                .select('id,first_name,last_name,email,student_id')
                .in_('id', student_ids)
                .execute())
            for s in (students_resp.data or []):
                student_map[s['id']] = s

        # Build leaderboard — best attempt per student
        best_per_student = {}
        for a in attempts:
            sid = a.get('student_id')
            if not sid:
                continue
            pct = a.get('percentage')
            if pct is None and a.get('total_marks') and float(a.get('total_marks', 0)) > 0:
                pct = round(float(a.get('score', 0)) / float(a['total_marks']) * 100, 1)
            if pct is None:
                continue
            if sid not in best_per_student or float(pct) > float(best_per_student[sid]['percentage']):
                best_per_student[sid] = {**a, 'percentage': float(pct)}

        ranked = sorted(best_per_student.values(), key=lambda x: -x['percentage'])[:limit]

        leaderboard = []
        for rank, entry in enumerate(ranked, 1):
            sid = entry.get('student_id')
            student = student_map.get(sid, {})
            full_name = f"{student.get('first_name','')} {student.get('last_name','')}".strip() or student.get('email', 'Student')
            leaderboard.append({
                'rank': rank,
                'student_id': student.get('student_id', ''),
                'name': full_name,
                'email': student.get('email', ''),
                'score': entry.get('score', 0),
                'total_marks': entry.get('total_marks', 0),
                'percentage': entry['percentage'],
                'submitted_at': entry.get('submitted_at'),
                'attempt_id': entry.get('attempt_id'),
            })

        # Compute stats
        all_pcts = [e['percentage'] for e in best_per_student.values()]
        stats = {
            'total_submissions': len(attempts),
            'unique_students': len(best_per_student),
            'avg_score': round(sum(all_pcts) / len(all_pcts), 1) if all_pcts else 0,
            'pass_rate': round(100 * sum(1 for p in all_pcts if p >= 50) / len(all_pcts), 1) if all_pcts else 0,
            'highest': max(all_pcts) if all_pcts else 0,
            'lowest': min(all_pcts) if all_pcts else 0,
        }
        return jsonify({'success': True, 'leaderboard': leaderboard, 'stats': stats, 'exam_id': exam_id}), 200
    except Exception as e:
        logger.error('[exam/leaderboard] Error: %s', e)
        return jsonify({'success': False, 'error': str(e), 'leaderboard': []}), 500


# ==========================================
# ROUTE: Teacher Per-Course Analytics
# ==========================================
@app.route('/api/teacher/course-analytics', methods=['GET'])
def teacher_course_analytics():
    """Per-course stats for a teacher: avg score, attempts, pass rate."""
    try:
        user_ctx, auth_error = _require_authenticated_roles('teacher', 'admin')
        if auth_error:
            return auth_error

        supabase = get_supabase()
        teacher_id = _user_ctx_profile_id(user_ctx)

        # Get teacher's courses
        courses_resp = db_exec(lambda: supabase.table('courses')
            .select('id,course_code,course_name')
            .eq('teacher_id', teacher_id)
            .execute())
        courses = courses_resp.data or []

        if not courses:
            return jsonify({'success': True, 'courses': []}), 200

        course_ids = [c['id'] for c in courses if c.get('id')]

        # Get exams for these courses
        exams_resp = db_exec(lambda: supabase.table('exams')
            .select('exam_id,course_id,exam_title,status')
            .in_('course_id', course_ids)
            .execute())
        exams = exams_resp.data or []

        exam_ids = [e['exam_id'] for e in exams if e.get('exam_id')]
        exam_to_course = {e['exam_id']: e['course_id'] for e in exams}

        # Get all attempts for these exams
        attempts_data = []
        if exam_ids:
            attempts_resp = db_exec(lambda: supabase.table('exam_attempts')
                .select('exam_id,percentage,status,student_id')
                .in_('exam_id', exam_ids)
                .in_('status', ['graded', 'completed', 'submitted', 'pending_grading'])
                .execute())
            attempts_data = attempts_resp.data or []

        # Get enrollment counts per course
        enr_resp = db_exec(lambda: supabase.table('enrollments')
            .select('course_id,student_id')
            .in_('course_id', course_ids)
            .execute())
        enrollments = enr_resp.data or []
        enr_count = {}
        for e in enrollments:
            cid = e.get('course_id')
            if cid:
                enr_count[cid] = enr_count.get(cid, 0) + 1

        # Aggregate per course
        course_stats = {c['id']: {
            'course_id': c['id'],
            'course_code': c.get('course_code', ''),
            'course_name': c.get('course_name', ''),
            'enrolled_students': enr_count.get(c['id'], 0),
            'total_exams': 0,
            'total_attempts': 0,
            'avg_score': 0,
            'pass_rate': 0,
            'highest_score': 0,
            '_scores': [],
        } for c in courses}

        for e in exams:
            cid = e.get('course_id')
            if cid in course_stats:
                course_stats[cid]['total_exams'] += 1

        for a in attempts_data:
            cid = exam_to_course.get(a.get('exam_id'))
            if cid and cid in course_stats:
                pct = a.get('percentage')
                if pct is not None:
                    course_stats[cid]['_scores'].append(float(pct))
                course_stats[cid]['total_attempts'] += 1

        result = []
        for cs in course_stats.values():
            scores = cs.pop('_scores')
            if scores:
                cs['avg_score'] = round(sum(scores) / len(scores), 1)
                cs['pass_rate'] = round(100 * sum(1 for s in scores if s >= 50) / len(scores), 1)
                cs['highest_score'] = round(max(scores), 1)
            result.append(cs)

        result.sort(key=lambda x: -x['total_attempts'])
        return jsonify({'success': True, 'courses': result}), 200
    except Exception as e:
        logger.error('[teacher/course-analytics] Error: %s', e)
        return jsonify({'success': False, 'error': str(e), 'courses': []}), 500



@app.route('/api/admin/cleanup-empty-exams', methods=['DELETE'])
def cleanup_empty_exams():
    """Delete exams that don't have questions (dangerous - use with caution)"""
    try:
        state, identity, auth_error = _require_active_admin(request.get_json(silent=True) or {})
        if auth_error:
            return auth_error
        supabase = get_supabase()
       
        # Get all exams
        exams_resp = supabase.table('exams').select('exam_id').execute()
        exams = exams_resp.data if exams_resp.data else []
       
        # Get all questions
        questions_resp = supabase.table('questions').select('exam_id').execute()
        questions = questions_resp.data if questions_resp.data else []
       
        # Find exams with questions
        exam_ids_with_questions = set([q['exam_id'] for q in questions])
       
        # Find exams without questions
        exams_without_questions = [e['exam_id'] for e in exams if e['exam_id'] not in exam_ids_with_questions]
       
        # Delete empty exams
        deleted_count = 0
        for exam_id in exams_without_questions:
            supabase.table('exams').delete().eq('exam_id', exam_id).execute()
            deleted_count += 1
       
        return jsonify({
            'status': 'success',
            'deleted': deleted_count,
            'exam_ids': exams_without_questions,
            'message': f'Deleted {deleted_count} exams without questions'
        }), 200
       
    except Exception as e:
        logger.error("Error cleaning up exams: %s", e)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/admin/access-check', methods=['POST'])
def admin_access_check():
    try:
        user_ctx, auth_error = _require_authenticated_user()
        if auth_error:
            return auth_error
        state = load_admin_control()
        email = user_ctx.get('email')
        admin_id = user_ctx.get('admin_id')
        role   = str(user_ctx.get('role') or '').strip().lower()
        status = str(user_ctx.get('status') or '').strip().lower()

        # Any active admin in the database is authorized — no JSON file check
        allowed = (role == 'admin' and status == 'active')
        active  = allowed and is_active_admin(state, email, admin_id)

        return jsonify({
            'success': True,
            'authorized': allowed,
            'active_admin': active,
            'identity': {'email': email, 'admin_id': admin_id},
            'summary': public_summary(state)
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/control', methods=['GET'])
def admin_control_summary():
    try:
        state, identity, auth_error = _require_active_admin()
        if auth_error:
            return auth_error
        return jsonify({
            'success': True,
            'control': public_summary(state)
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/courses', methods=['GET'])
def admin_list_courses():
    try:
        state, identity, auth_error = _require_authorized_admin()
        if auth_error:
            return auth_error
        supabase = get_supabase()
        resp = db_exec(
            lambda: supabase.table('courses')
            .select('id,course_code,course_name,semester,academic_year,teacher_id')
            .order('course_code')
            .limit(500)
            .execute()
        )
        courses = [_serialize_course_summary(row) for row in (resp.data or [])]
        return jsonify({'success': True, 'courses': courses}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'courses': []}), 500


@app.route('/api/admin/users/<student_identifier>/courses', methods=['GET'])
def admin_get_student_courses(student_identifier):
    try:
        state, identity, auth_error = _require_authorized_admin()
        if auth_error:
            return auth_error
        supabase = get_supabase()
        student_row = _load_user_row_by_identifier(
            supabase,
            student_identifier,
            'id,student_id,email,first_name,last_name,role,status'
        )
        if not student_row:
            return jsonify({'success': False, 'error': 'Student account not found', 'course_ids': [], 'courses': []}), 404
        if str(student_row.get('role') or '').strip().lower() != 'student':
            return jsonify({'success': False, 'error': 'Selected user is not a student', 'course_ids': [], 'courses': []}), 400

        student_id = str(student_row.get('id') or student_row.get('student_id') or '').strip()
        enrollments = _load_student_enrollments(supabase, student_id)
        course_ids = [str(row.get('course_id') or '').strip() for row in enrollments if row.get('course_id')]
        if not course_ids:
            return jsonify({
                'success': True,
                'student': {
                    'id': student_id,
                    'email': student_row.get('email'),
                    'name': ' '.join([str(student_row.get('first_name') or '').strip(), str(student_row.get('last_name') or '').strip()]).strip() or 'Student'
                },
                'course_ids': [],
                'courses': []
            }), 200
        course_resp = db_exec(
            lambda: supabase.table('courses')
            .select('id,course_code,course_name,semester,academic_year,teacher_id')
            .in_('id', course_ids)
            .execute()
        )
        course_map = {
            str((row.get('id') or row.get('course_id') or '')).strip(): dict(row or {})
            for row in (course_resp.data or [])
        }
        courses = []
        for course_id in course_ids:
            course_row = course_map.get(course_id)
            if course_row:
                courses.append(_serialize_course_summary(course_row))

        return jsonify({
            'success': True,
            'student': {
                'id': student_id,
                'email': student_row.get('email'),
                'name': ' '.join([str(student_row.get('first_name') or '').strip(), str(student_row.get('last_name') or '').strip()]).strip() or 'Student'
            },
            'course_ids': course_ids,
            'courses': courses
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'course_ids': [], 'courses': []}), 500


@app.route('/api/admin/users/<student_identifier>/courses', methods=['PUT'])
def admin_update_student_courses(student_identifier):
    try:
        data = request.get_json(silent=True) or {}
        state, identity, auth_error = _require_authorized_admin(data)
        if auth_error:
            return auth_error

        requested_course_ids = data.get('course_ids')
        if not isinstance(requested_course_ids, list):
            return jsonify({'success': False, 'error': 'course_ids must be an array'}), 400

        normalized_course_ids = []
        seen_course_ids = set()
        for raw_course_id in requested_course_ids:
            course_id = str(raw_course_id or '').strip()
            if not course_id:
                continue
            if not _is_valid_uuid(course_id):
                return jsonify({'success': False, 'error': f'Invalid course id: {course_id}'}), 400
            if course_id in seen_course_ids:
                continue
            normalized_course_ids.append(course_id)
            seen_course_ids.add(course_id)

        supabase = get_supabase()
        student_row = _load_user_row_by_identifier(
            supabase,
            student_identifier,
            'id,student_id,email,first_name,last_name,role,status'
        )
        if not student_row:
            return jsonify({'success': False, 'error': 'Student account not found'}), 404
        if str(student_row.get('role') or '').strip().lower() != 'student':
            return jsonify({'success': False, 'error': 'Selected user is not a student'}), 400

        student_id = str(student_row.get('id') or student_row.get('student_id') or '').strip()
        if not student_id:
            return jsonify({'success': False, 'error': 'Student profile id is missing'}), 400

        requested_courses = []
        for course_id in normalized_course_ids:
            course_row = _load_course_row(supabase, course_id, 'id,course_code,course_name,semester,academic_year,teacher_id')
            if not course_row:
                return jsonify({'success': False, 'error': f'Course not found: {course_id}'}), 404
            requested_courses.append(course_row)

        existing_resp = db_exec(
            lambda: supabase.table('enrollments')
            .select('enrollment_id,course_id,status')
            .eq('student_id', student_id)
            .execute()
        )
        existing_rows = [dict(row or {}) for row in (existing_resp.data or [])]
        existing_by_course = {
            str(row.get('course_id') or '').strip(): row
            for row in existing_rows
            if row.get('course_id')
        }

        requested_set = set(normalized_course_ids)
        for row in existing_rows:
            course_id = str(row.get('course_id') or '').strip()
            enrollment_id = row.get('enrollment_id')
            if course_id and course_id not in requested_set and enrollment_id:
                db_exec(lambda enrollment_id=enrollment_id: supabase.table('enrollments').delete().eq('enrollment_id', enrollment_id).execute())

        for course_id in normalized_course_ids:
            existing_row = existing_by_course.get(course_id)
            if existing_row and existing_row.get('enrollment_id'):
                _activate_enrollment_record(supabase, existing_row.get('enrollment_id'))
                continue
            _create_active_enrollment_record(supabase, student_id, course_id)

        return jsonify({
            'success': True,
            'message': 'Student course assignments updated',
            'student_id': student_id,
            'course_ids': normalized_course_ids,
            'courses': [_serialize_course_summary(course_row) for course_row in requested_courses]
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/teachers/<teacher_identifier>/courses', methods=['GET'])
def admin_get_teacher_courses(teacher_identifier):
    try:
        state, identity, auth_error = _require_authorized_admin()
        if auth_error:
            return auth_error
        supabase = get_supabase()
        teacher_row = _load_user_row_by_identifier(
            supabase,
            teacher_identifier,
            'id,teacher_id,email,first_name,last_name,role,status'
        )
        if not teacher_row:
            return jsonify({'success': False, 'error': 'Teacher account not found', 'course_ids': [], 'courses': []}), 404
        if str(teacher_row.get('role') or '').strip().lower() != 'teacher':
            return jsonify({'success': False, 'error': 'Selected user is not a teacher', 'course_ids': [], 'courses': []}), 400

        teacher_id = str(teacher_row.get('id') or teacher_row.get('teacher_id') or '').strip()
        if not teacher_id:
            return jsonify({'success': False, 'error': 'Teacher profile id is missing', 'course_ids': [], 'courses': []}), 400

        course_resp = db_exec(
            lambda: supabase.table('courses')
            .select('id,course_code,course_name,semester,academic_year,teacher_id')
            .eq('teacher_id', teacher_id)
            .execute()
        )
        courses = [_serialize_course_summary(row) for row in (course_resp.data or [])]
        course_ids = [str((row.get('id') or row.get('course_id') or '')).strip() for row in (course_resp.data or []) if row.get('id') or row.get('course_id')]

        return jsonify({
            'success': True,
            'teacher': {
                'id': teacher_id,
                'email': teacher_row.get('email'),
                'name': ' '.join([str(teacher_row.get('first_name') or '').strip(), str(teacher_row.get('last_name') or '').strip()]).strip() or 'Teacher'
            },
            'course_ids': course_ids,
            'courses': courses
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'course_ids': [], 'courses': []}), 500


@app.route('/api/admin/teachers/<teacher_identifier>/courses', methods=['PUT'])
def admin_update_teacher_courses(teacher_identifier):
    try:
        data = request.get_json(silent=True) or {}
        state, identity, auth_error = _require_authorized_admin(data)
        if auth_error:
            return auth_error

        requested_course_ids = data.get('course_ids')
        if not isinstance(requested_course_ids, list):
            return jsonify({'success': False, 'error': 'course_ids must be an array'}), 400

        normalized_course_ids = []
        seen_course_ids = set()
        for raw_course_id in requested_course_ids:
            course_id = str(raw_course_id or '').strip()
            if not course_id:
                continue
            if not _is_valid_uuid(course_id):
                return jsonify({'success': False, 'error': f'Invalid course id: {course_id}'}), 400
            if course_id in seen_course_ids:
                continue
            normalized_course_ids.append(course_id)
            seen_course_ids.add(course_id)

        supabase = get_supabase()
        teacher_row = _load_user_row_by_identifier(
            supabase,
            teacher_identifier,
            'id,teacher_id,email,first_name,last_name,role,status'
        )
        if not teacher_row:
            return jsonify({'success': False, 'error': 'Teacher account not found'}), 404
        if str(teacher_row.get('role') or '').strip().lower() != 'teacher':
            return jsonify({'success': False, 'error': 'Selected user is not a teacher'}), 400

        teacher_id = str(teacher_row.get('id') or teacher_row.get('teacher_id') or '').strip()
        if not teacher_id:
            return jsonify({'success': False, 'error': 'Teacher profile id is missing'}), 400

        requested_courses = []
        for course_id in normalized_course_ids:
            course_row = _load_course_row(supabase, course_id, 'id,course_code,course_name,semester,academic_year,teacher_id')
            if not course_row:
                return jsonify({'success': False, 'error': f'Course not found: {course_id}'}), 404
            requested_courses.append(course_row)

        existing_resp = db_exec(
            lambda: supabase.table('courses')
            .select('id,teacher_id')
            .eq('teacher_id', teacher_id)
            .execute()
        )
        existing_rows = [dict(row or {}) for row in (existing_resp.data or [])]
        existing_course_ids = {
            str(row.get('id') or row.get('course_id') or '').strip()
            for row in existing_rows
            if row.get('id') or row.get('course_id')
        }

        requested_set = set(normalized_course_ids)
        for course_id in existing_course_ids:
            if course_id and course_id not in requested_set:
                # Only unassign if the DB allows NULL teacher_id
                try:
                    db_exec(lambda course_id=course_id: supabase.table('courses').update({'teacher_id': None}).eq('id', course_id).execute())
                except Exception:
                    pass  # Skip if NOT NULL constraint prevents it

        for course_id in normalized_course_ids:
            db_exec(lambda course_id=course_id: supabase.table('courses').update({'teacher_id': teacher_id}).eq('id', course_id).execute())

        return jsonify({
            'success': True,
            'message': 'Teacher course assignments updated',
            'teacher_id': teacher_id,
            'course_ids': normalized_course_ids,
            'courses': [_serialize_course_summary(course_row) for course_row in requested_courses]
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/transfer', methods=['POST'])
def admin_transfer_control():
    try:
        data = request.get_json(silent=True) or {}
        state, identity, auth_error = _require_active_admin(data)
        if auth_error:
            return auth_error

        successor_email = (data.get('successor_email') or '').strip().lower()
        successor_admin_id = (data.get('successor_admin_id') or '').strip()
        if not successor_email or not successor_admin_id:
            return jsonify({'success': False, 'error': 'successor_email and successor_admin_id are required'}), 400

        supabase = get_supabase()
        user_resp = db_exec(lambda: supabase.table('users').select('*').eq('email', successor_email).limit(1).execute())
        if not user_resp.data:
            return jsonify({'success': False, 'error': 'Successor account not found'}), 404

        successor = user_resp.data[0]
        if str(successor.get('status') or '').lower() != 'active':
            return jsonify({'success': False, 'error': 'Successor account must be active'}), 400

        update_payload = {'role': 'admin', 'admin_id': successor_admin_id}
        db_exec(lambda: supabase.table('users').update(update_payload).eq('email', successor_email).execute())

        previous_admin = dict(state.get('active_admin') or {})
        state['active_admin'] = {
            'email': successor_email,
            'admin_id': successor_admin_id,
        }
        state['authorized_admins'] = [{
            'email': successor_email,
            'admin_id': successor_admin_id,
        }]
        record_transfer(state, identity.get('email'), previous_admin, state['active_admin'])
        save_admin_control(state)

        previous_email = (previous_admin.get('email') or '').strip().lower()
        if previous_email and previous_email != successor_email:
            try:
                db_exec(lambda: supabase.table('users').update({'role': 'teacher'}).eq('email', previous_email).execute())
            except Exception:
                pass

        return jsonify({
            'success': True,
            'message': 'Admin control transferred successfully',
            'control': public_summary(state)
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# ROUTE: Bulk CSV Student Enrollment
# ==========================================
@app.route('/api/admin/enroll-csv', methods=['POST'])
def admin_enroll_csv():
    """
    Bulk enroll students from a CSV file.
    CSV format: email,course_code  (header row optional)
    Also accepts JSON: {"rows": [{"email":"...","course_code":"..."}]}
    Returns per-row results.
    """
    try:
        state, identity, auth_error = _require_authorized_admin()
        if auth_error:
            return auth_error

        supabase = get_supabase()
        rows = []

        # ── Parse input ───────────────────────────────────────────
        if request.content_type and 'multipart' in request.content_type:
            # File upload
            csv_file = request.files.get('file')
            if not csv_file:
                return jsonify({'success': False, 'error': 'No file uploaded'}), 400
            import io, csv as _csv
            content = csv_file.read().decode('utf-8-sig', errors='replace')
            reader  = _csv.reader(io.StringIO(content))
            for line in reader:
                if not line:
                    continue
                # Skip header row
                if line[0].strip().lower() in ('email', 'student_email', '#'):
                    continue
                if len(line) >= 2:
                    rows.append({'email': line[0].strip().lower(), 'course_code': line[1].strip().upper()})
        else:
            # JSON body
            data = request.get_json(silent=True) or {}
            rows = data.get('rows', [])

        if not rows:
            return jsonify({'success': False, 'error': 'No enrollment rows provided'}), 400

        # ── Pre-load course map ───────────────────────────────────
        all_courses = db_exec(lambda: supabase.table('courses').select('id,course_code').execute())
        course_map  = {c['course_code'].upper(): c['id'] for c in (all_courses.data or []) if c.get('course_code')}

        results_list = []
        enrolled_count = 0
        skipped_count  = 0
        error_count    = 0

        for row in rows:
            email       = str(row.get('email') or '').strip().lower()
            course_code = str(row.get('course_code') or '').strip().upper()

            if not email or not course_code:
                results_list.append({'email': email, 'course_code': course_code, 'status': 'error', 'reason': 'Missing email or course_code'})
                error_count += 1
                continue

            # Find student
            user_r = db_exec(lambda: supabase.table('users').select('id,status,role').eq('email', email).limit(1).execute())
            if not user_r.data:
                results_list.append({'email': email, 'course_code': course_code, 'status': 'error', 'reason': 'Student not found'})
                error_count += 1
                continue

            user = user_r.data[0]
            if str(user.get('role') or '').lower() != 'student':
                results_list.append({'email': email, 'course_code': course_code, 'status': 'error', 'reason': 'User is not a student'})
                error_count += 1
                continue

            student_id = str(user.get('id') or '').strip()
            course_id  = course_map.get(course_code)
            if not course_id:
                results_list.append({'email': email, 'course_code': course_code, 'status': 'error', 'reason': f'Course {course_code} not found'})
                error_count += 1
                continue

            # Check existing enrollment
            existing = db_exec(lambda: supabase.table('enrollments').select('enrollment_id,status').eq('student_id', student_id).eq('course_id', course_id).limit(1).execute())
            if existing.data:
                # Already enrolled — activate if not active
                enroll_id = existing.data[0].get('enrollment_id')
                if str(existing.data[0].get('status') or '').lower() != 'active':
                    _activate_enrollment_record(supabase, enroll_id)
                results_list.append({'email': email, 'course_code': course_code, 'status': 'skipped', 'reason': 'Already enrolled'})
                skipped_count += 1
                continue

            # Create enrollment
            try:
                _create_active_enrollment_record(supabase, student_id, course_id)
                results_list.append({'email': email, 'course_code': course_code, 'status': 'enrolled'})
                enrolled_count += 1
            except Exception as enroll_err:
                results_list.append({'email': email, 'course_code': course_code, 'status': 'error', 'reason': str(enroll_err)[:80]})
                error_count += 1

        return jsonify({
            'success': True,
            'summary': {
                'total': len(rows),
                'enrolled': enrolled_count,
                'skipped': skipped_count,
                'errors': error_count
            },
            'results': results_list
        }), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/users', methods=['GET'])
def admin_list_users():
    try:
        state, identity, auth_error = _require_authorized_admin()
        if auth_error:
            return auth_error
        supabase = get_supabase()
        resp = db_exec(lambda: supabase.table('users').select('*').order('created_at', desc=True).limit(500).execute())
        return jsonify({
            'success': True,
            'users': resp.data or []
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'users': []}), 500


@app.route('/api/admin/users/status', methods=['PUT'])
def admin_update_user_status():
    try:
        data = request.get_json(silent=True) or {}
        state, identity, auth_error = _require_authorized_admin(data)
        if auth_error:
            return auth_error

        user_email = (data.get('user_email') or data.get('email') or '').strip().lower()
        status = (data.get('status') or '').strip().lower()
        if not user_email or status not in ('active', 'suspended', 'pending', 'rejected'):
            return jsonify({'success': False, 'error': 'user_email and valid status (active/suspended/pending/rejected) are required'}), 400

        active_email = (state.get('active_admin', {}).get('email') or '').strip().lower()
        if user_email == active_email and status != 'active':
            return jsonify({'success': False, 'error': 'Active admin cannot be suspended from this screen'}), 400

        supabase = get_supabase()
        db_exec(lambda: supabase.table('users').update({'status': status}).eq('email', user_email).execute())

        # ── Email: notify user of status change ────────────────────
        try:
            from utils.email_notify import notify_account_approved, notify_account_suspended
            user_r = db_exec(lambda: supabase.table('users').select(
                'first_name,last_name,role'
            ).eq('email', user_email).limit(1).execute())
            if user_r.data:
                u = user_r.data[0]
                u_name = f"{u.get('first_name','')} {u.get('last_name','')}".strip() or user_email
                import threading
                if status == 'active':
                    threading.Thread(
                        target=notify_account_approved,
                        args=(user_email, u_name, u.get('role', 'user')),
                        daemon=True
                    ).start()
                elif status == 'suspended':
                    threading.Thread(
                        target=notify_account_suspended,
                        args=(user_email, u_name),
                        daemon=True
                    ).start()
                elif status == 'rejected':
                    # Send rejection email
                    from utils.email_notify import _send, _base_template, APP_URL
                    body = f"""
                        <p>Dear {u_name},</p>
                        <p>We regret to inform you that your registration request for the Smart Exam System has been <strong>rejected</strong> by the administrator.</p>
                        <p>If you believe this is an error, please contact your institution's administrator.</p>
                    """
                    html = _base_template("Registration Request Rejected", body)
                    threading.Thread(target=_send, args=(user_email, "Smart Exam System — Registration Rejected", html), daemon=True).start()
        except Exception as email_err:
            logger.warning("[email] Status change notification failed: %s", email_err)

        return jsonify({'success': True, 'message': 'User status updated'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    """
    Public registration endpoint.
    Creates Supabase auth user + inserts profile using service role key (bypasses RLS).
    Returns success even if email confirmation is pending.
    """
    try:
        data = request.get_json(silent=True) or {}

        email      = str(data.get('email') or '').strip().lower()
        password   = str(data.get('password') or '').strip()
        first_name = str(data.get('first_name') or '').strip()
        last_name  = str(data.get('last_name') or '').strip()
        role       = str(data.get('role') or '').strip().lower()

        if not email or not password or not first_name or not role:
            return jsonify({'success': False, 'error': 'email, password, first_name and role are required'}), 400

        if role not in ('student', 'teacher'):
            return jsonify({'success': False, 'error': 'Only student and teacher registration is allowed'}), 400

        if len(password) < 8:
            return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400

        # Use service role client to bypass RLS
        service_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY')
        supabase_url = os.getenv('SUPABASE_URL')
        if not service_key or not supabase_url:
            return jsonify({'success': False, 'error': 'Server configuration error'}), 500

        from supabase import create_client
        admin_client = create_client(supabase_url, service_key)

        # Check if email already exists in users table
        existing = db_exec(lambda: admin_client.table('users').select('id').eq('email', email).limit(1).execute())
        if existing.data:
            return jsonify({'success': False, 'error': 'An account with this email already exists'}), 409

        # Create Supabase auth user
        auth_user_id = None
        try:
            auth_resp = admin_client.auth.admin.create_user({
                'email': email,
                'password': password,
                'email_confirm': True,   # auto-confirm so login works immediately
            })
            auth_user = getattr(auth_resp, 'user', None) or (auth_resp if isinstance(auth_resp, dict) else None)
            if auth_user:
                auth_user_id = str(getattr(auth_user, 'id', '') or (auth_user.get('id') if isinstance(auth_user, dict) else '') or '').strip() or None
        except Exception as auth_err:
            logger.warning("[register] Auth user creation failed: %s", auth_err)
            # Continue — profile can still be inserted without auth_id

        # Build profile row
        profile = {
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'full_name': f"{first_name} {last_name}".strip(),
            'role': role,
            'status': 'pending',
        }
        if auth_user_id:
            profile['auth_id'] = auth_user_id

        # Optional fields
        for field in ('student_id', 'teacher_id', 'batch', 'department'):
            val = str(data.get(field) or '').strip()
            if val:
                profile[field] = val

        # Insert profile using service role (bypasses RLS)
        insert_resp = db_exec(lambda: admin_client.table('users').insert(profile).execute())
        if not insert_resp.data:
            return jsonify({'success': False, 'error': 'Failed to save user profile'}), 500

        # Notify admins (non-blocking)
        try:
            from utils.email_notify import _send, _base_template, APP_URL
            admins = db_exec(lambda: admin_client.table('users').select('email').eq('role', 'admin').eq('status', 'active').execute())
            admin_emails = [a.get('email') for a in (admins.data or []) if a.get('email')]
            full_name = profile['full_name']
            body = f"""
                <p>A new user has registered and is awaiting your approval.</p>
                <table style="width:100%;border-collapse:collapse;margin:16px 0;">
                  <tr style="background:#f1f5f9;"><td style="padding:10px;font-weight:700;">Name</td><td style="padding:10px;">{full_name}</td></tr>
                  <tr><td style="padding:10px;font-weight:700;">Email</td><td style="padding:10px;">{email}</td></tr>
                  <tr style="background:#f1f5f9;"><td style="padding:10px;font-weight:700;">Role</td><td style="padding:10px;">{role.title()}</td></tr>
                  <tr><td style="padding:10px;font-weight:700;">Status</td><td style="padding:10px;color:#d97706;font-weight:700;">Pending Approval</td></tr>
                </table>
                <a href="{APP_URL}/manage-users.html">Review in Admin Panel</a>
            """
            html = _base_template("New User Registration — Action Required", body)
            import threading
            for admin_email in admin_emails:
                threading.Thread(target=_send, args=(admin_email, f"New {role.title()} Registration: {full_name}", html), daemon=True).start()
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Registration submitted. Awaiting admin approval.'}), 201

    except Exception as e:
        logger.error("[register] Unexpected error: %s", e)
        return jsonify({'success': False, 'error': 'Registration failed. Please try again.'}), 500


@app.route('/api/auth/notify-signup', methods=['POST'])
def notify_signup():
    """
    Called by frontend after a new user registers.
    Notifies all active admins that a new account is pending approval.
    No auth required — public endpoint (rate-limited by Supabase auth).
    """
    try:
        data = request.get_json(silent=True) or {}
        new_email = str(data.get('email') or '').strip().lower()
        new_name  = str(data.get('name')  or '').strip()
        new_role  = str(data.get('role')  or 'user').strip()

        if not new_email:
            return jsonify({'success': False, 'error': 'email required'}), 400

        # Notify all active admins
        try:
            from utils.email_notify import _send, _base_template, APP_URL
            supabase = get_supabase()
            admins = db_exec(lambda: supabase.table('users').select('email').eq('role', 'admin').eq('status', 'active').execute())
            admin_emails = [a.get('email') for a in (admins.data or []) if a.get('email')]

            body = f"""
                <p>A new user has registered and is awaiting your approval.</p>
                <table style="width:100%;border-collapse:collapse;margin:16px 0;">
                  <tr style="background:#f1f5f9;"><td style="padding:10px;font-weight:700;">Name</td><td style="padding:10px;">{new_name}</td></tr>
                  <tr><td style="padding:10px;font-weight:700;">Email</td><td style="padding:10px;">{new_email}</td></tr>
                  <tr style="background:#f1f5f9;"><td style="padding:10px;font-weight:700;">Role</td><td style="padding:10px;">{new_role.title()}</td></tr>
                  <tr><td style="padding:10px;font-weight:700;">Status</td><td style="padding:10px;color:#d97706;font-weight:700;">Pending Approval</td></tr>
                </table>
                <a href="{APP_URL}/manage-users.html" class="btn">Review in Admin Panel</a>
            """
            html = _base_template("New User Registration — Action Required", body)
            import threading
            for admin_email in admin_emails:
                threading.Thread(
                    target=_send,
                    args=(admin_email, f"New {new_role.title()} Registration: {new_name}", html),
                    daemon=True
                ).start()
        except Exception as email_err:
            logger.warning("[email] Admin signup notification failed: %s", email_err)

        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/session/acquire', methods=['POST'])
def auth_session_acquire():
    try:
        data = request.get_json(silent=True) or {}
        identity, auth_error = _require_session_lock_payload(data)
        if auth_error:
            return auth_error
        force_takeover = bool(data.get('force_takeover') or data.get('takeover'))
        state = load_session_locks()
        success, error, lock = acquire_session_lock(
            state,
            identity.get('email'),
            identity.get('role'),
            identity.get('device_id'),
            force_takeover=force_takeover,
        )
        if not success:
            return jsonify({'success': False, 'error': error, 'lock': lock}), 409
        save_session_locks(state)
        return jsonify({'success': True, 'lock': lock, 'taken_over': force_takeover}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/session/renew', methods=['POST'])
def auth_session_renew():
    try:
        data = request.get_json(silent=True) or {}
        identity, auth_error = _require_session_lock_payload(data)
        if auth_error:
            return auth_error
        state = load_session_locks()
        success, error, lock = renew_session_lock(
            state,
            identity.get('email'),
            identity.get('role'),
            identity.get('device_id'),
        )
        if not success:
            return jsonify({'success': False, 'error': error, 'lock': lock}), 409
        save_session_locks(state)
        return jsonify({'success': True, 'lock': lock}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/session/release', methods=['POST'])
def auth_session_release():
    try:
        data = request.get_json(silent=True) or {}
        state = load_session_locks()
        released = release_session_lock(
            state,
            data.get('email'),
            data.get('role'),
            data.get('device_id'),
        )
        if released:
            save_session_locks(state)
        return jsonify({'success': released}), 200 if released else 409
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# ROUTE: Cleanup Old Uploads (legacy alias)
# ==========================================
@app.route('/api/uploads/cleanup', methods=['POST'])
def cleanup_old_uploads_legacy():
    """Legacy alias — redirects to /api/admin/cleanup-uploads."""
    return cleanup_old_uploads()


# ==========================================
# ROUTE: AI Chatbot (Grok via xAI API)
# ==========================================
@app.route('/api/chatbot', methods=['POST'])
def chatbot():
    """
    Proxy to xAI Grok API — keeps API key secure on server.
    Request JSON: { "messages": [...], "role": "student|teacher|admin" }
    Auth is optional — role falls back to header or request body.
    """
    try:
        # Auth is completely optional for chatbot — never block on auth failure
        user_ctx = None
        try:
            ctx, auth_error = _optional_authenticated_user()
            if not auth_error:
                user_ctx = ctx
        except Exception:
            pass

        data = request.get_json(silent=True) or {}
        messages = data.get('messages', [])

        # Determine role from auth context, header, or body
        user_role = 'student'
        if user_ctx:
            user_role = str((user_ctx or {}).get('role') or 'student').strip().lower()
        else:
            user_role = str(
                request.headers.get('X-User-Role') or
                data.get('role') or
                'student'
            ).strip().lower()

        # Accept both 'message' (string) and 'messages' (array) for flexibility
        if not messages:
            single_msg = data.get('message', '').strip()
            if single_msg:
                messages = [{'role': 'user', 'content': single_msg}]

        if not messages:
            return jsonify({'error': 'messages are required'}), 400

        # Limit message history to last 10 to control token usage
        messages = messages[-10:]

        # System prompt tailored to role
        role_context = {
            'student': (
                "You are a helpful AI assistant for the Smart Exam System. "
                "You help students understand exam topics, explain concepts, "
                "and guide them through their coursework. "
                "Be encouraging, clear, and educational. "
                "Do NOT give direct answers to exam questions — instead guide students to think."
            ),
            'teacher': (
                "You are an AI assistant for teachers on the Smart Exam System. "
                "You help teachers create better exam questions, understand student performance, "
                "provide grading guidance, and suggest teaching strategies. "
                "Be professional and pedagogically sound."
            ),
            'admin': (
                "You are an AI assistant for system administrators on the Smart Exam System. "
                "You help with user management, system configuration, analytics interpretation, "
                "and platform operations. Be concise and technical."
            ),
        }
        system_prompt = role_context.get(user_role, role_context['student'])

        # Add system message at the start
        full_messages = [{'role': 'system', 'content': system_prompt}] + messages

        # Call xAI Grok API
        xai_api_key = os.getenv('XAI_API_KEY', '')

        import requests as _req

        if xai_api_key:
            try:
                resp = _req.post(
                    'https://api.x.ai/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {xai_api_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': 'grok-3-mini',
                        'messages': full_messages,
                        'temperature': 0.7,
                        'max_tokens': 1024,
                        'stream': False
                    },
                    timeout=30
                )

                if resp.status_code == 200:
                    result = resp.json()
                    reply = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                    usage  = result.get('usage', {})
                    return jsonify({'success': True, 'reply': reply, 'usage': usage, 'model': 'grok-3-mini'}), 200

                logger.warning("[chatbot] xAI API error %s: %s", resp.status_code, resp.text[:200])
                # Fall through to Ollama fallback
            except Exception as xai_err:
                logger.warning("[chatbot] xAI call failed: %s", xai_err)
                # Fall through to Ollama fallback

        # ── Fallback: Ollama (local) ──────────────────────────────────
        from models.model_access import OLLAMA_BASE_URL, OLLAMA_MODEL_NAME, _OLLAMA_HEADERS, _ollama_available
        if _ollama_available():
            try:
                ollama_resp = _req.post(
                    f'{OLLAMA_BASE_URL}/api/chat',
                    headers=_OLLAMA_HEADERS,
                    json={
                        'model': OLLAMA_MODEL_NAME,
                        'messages': full_messages,
                        'stream': False,
                        'options': {'temperature': 0.7, 'num_predict': 512}
                    },
                    timeout=60
                )
                if ollama_resp.status_code == 200:
                    reply = ollama_resp.json().get('message', {}).get('content', '')
                    return jsonify({'success': True, 'reply': reply, 'usage': {}, 'model': OLLAMA_MODEL_NAME}), 200
            except Exception as ollama_err:
                logger.warning("[chatbot] Ollama fallback failed: %s", ollama_err)

        return jsonify({'error': 'AI chatbot is currently unavailable. Please try again later.'}), 503

    except Exception as e:
        logger.error("[chatbot] Error: %s", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
   
    print("\n" + "=" * 70)
    print("🤖 AI-BASED SMART EXAM WEB SYSTEM - BACKEND SERVER")
    print("=" * 70)
    print(f"📡 Server running on: http://localhost:{port}")
    print(f"🔗 API Base URL: http://localhost:{port}/api")
    print("\n📚 Available Models:")
    print(" ✅ Ollama Qwen 2.5 7B (Question Generation)")
    print(" ✅ Sentence-BERT (Essay Grading)")
    print(" ✅ BERTopic (Topic Extraction)")
    print("\n🌐 API Endpoints:")
    print(" GET /api/health")
    print(" POST /api/generate-questions")
    print(" POST /api/grade-essay")
    print(" POST /api/grade-batch")
    print(" POST /api/teacher-grade")
    print(" GET /api/grading-stats")
    print(" POST /api/extract-topics")
    print(" GET /api/models/info")
    print("=" * 70 + "\n")

    # ── Background model preloading ──────────────────────────────────
    # Heavy imports (torch, sentence_transformers, transformers) + model
    # loading take ~60 s on first use.  By preloading in a daemon thread
    # the server accepts requests immediately and models are usually
    # ready by the time a user navigates the UI and submits a request.
    import threading

    def _preload_models():
        import time as _t
        _start = _t.time()
        print("[preload] Background model loading started ...")
        preload_all_models()   # BERTopic, Subject-CLF, CodeBERT
        preload_sbert()        # Sentence-BERT for essay grading
        print(f"[preload] All models ready in {_t.time() - _start:.1f}s")

    _preload_thread = threading.Thread(target=_preload_models, daemon=True)
    _preload_thread.start()
   
    app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False)
