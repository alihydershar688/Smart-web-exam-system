import re
import json
import warnings
import sys
import os
import random
from collections import Counter
warnings.filterwarnings('ignore')
import re
import json
import warnings
import sys
import os
import random
from collections import Counter
warnings.filterwarnings('ignore')

# Ollama Qwen 2.5 7B model access
try:
    from models.model_access import generate_question_json as _ollama_generate, _ollama_available
except ImportError:
    try:
        from backend.models.model_access import generate_question_json as _ollama_generate, _ollama_available
    except ImportError:
        _ollama_generate = None
        _ollama_available = None

if _ollama_available is not None:
    try:
        from models.model_access import OLLAMA_BASE_URL as _ollama_url
    except ImportError:
        try:
            from backend.models.model_access import OLLAMA_BASE_URL as _ollama_url
        except ImportError:
            _ollama_url = "unknown"
    OLLAMA_AVAILABLE = _ollama_available()
    if OLLAMA_AVAILABLE:
        print(f"\u2713 Ollama Qwen 2.5 7B is reachable at {_ollama_url}")
    else:
        print(f"\u26a0\ufe0f Ollama not reachable at {_ollama_url} — will use rule-based fallback")
else:
    OLLAMA_AVAILABLE = False
    print("\u26a0\ufe0f model_access.py not found — Ollama disabled")

# ── Quality Improvements: Grounding, Validation, Duplicate Detection ───
try:
    from models.content_grounding import ContentGroundingEngine, ground_question
    from models.duplicate_detection import assess_question_duplicates
    from models.exam_validator import validate_exam_before_publishing
except ImportError:
    try:
        from backend.models.content_grounding import ContentGroundingEngine, ground_question
        from backend.models.duplicate_detection import assess_question_duplicates
        from backend.models.exam_validator import validate_exam_before_publishing
    except ImportError:
        # Graceful degradation if quality modules not available
        ContentGroundingEngine = None
        ground_question = lambda q, e: q  # No-op
        assess_question_duplicates = lambda qs: qs  # No-op
        validate_exam_before_publishing = lambda e, qs: (True, {'errors': [], 'warnings': []})

# Suppress PyTorch warnings
os.environ['PYTHONWARNINGS'] = 'ignore'
os.environ['TORCH_HOME'] = os.path.join(os.path.expanduser('~'), '.cache', 'torch')

# Resolve project root (two levels up from backend/models/)
_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)

TORCH_AVAILABLE = False
TRANSFORMERS_AVAILABLE = False
torch = None
AutoTokenizer = None
AutoModelForSeq2SeqLM = None
AutoModel = None
pipeline = None

def _try_import_torch():
    """Try to import torch with timeout handling"""
    global TORCH_AVAILABLE, TRANSFORMERS_AVAILABLE, torch, AutoTokenizer, AutoModelForSeq2SeqLM, AutoModel, pipeline

    try:
        import logging
        logging.getLogger("torch").setLevel(logging.ERROR)
        logging.getLogger("transformers").setLevel(logging.ERROR)

        import torch as torch_module
        from transformers import AutoTokenizer as AT, AutoModelForSeq2SeqLM as AMSLM, AutoModel as AM, pipeline as pl

        torch = torch_module
        AutoTokenizer = AT
        AutoModelForSeq2SeqLM = AMSLM
        AutoModel = AM
        pipeline = pl

        TORCH_AVAILABLE = True
        TRANSFORMERS_AVAILABLE = True
        return True
    except KeyboardInterrupt:
        print("⚠️ PyTorch import interrupted - using fallback mode")
        return False
    except Exception as e:
        print(f"⚠️ Torch/Transformers not available: {str(e)[:100]}")
        return False

# Try to import on module load
_try_import_torch()

# Load models (will download from Hugging Face on first run)
MODELS_LOADED = False
codebert_model = None
codebert_tokenizer = None
device = "cuda" if (TORCH_AVAILABLE and torch and torch.cuda.is_available()) else "cpu"


def _env_bool(name, default=False):
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in ("1", "true", "yes", "on")


USE_FINETUNED_MODELS = _env_bool("USE_FINETUNED_MODELS", False)

# ── Remote HF Space for GPU-accelerated generation ──────────────────────────
HF_SPACE_URL = os.getenv("HF_SPACE_URL", "").strip()

CODEBERT_MODEL_PATH = os.getenv(
    "CODEBERT_MODEL_PATH",
    os.path.join(_PROJECT_ROOT, "models", "codebert_finetuned"),
)
USE_QWEN_LORA = _env_bool("USE_QWEN_LORA", False)
QWEN_BASE_MODEL = os.getenv("QWEN_BASE_MODEL", "Qwen/Qwen2.5-Coder-1.5B-Instruct")
QWEN_LORA_PATH = os.getenv(
    "QWEN_LORA_PATH",
    os.path.join(_PROJECT_ROOT, "models", "qwen_lora_adapter"),
)

if TORCH_AVAILABLE and TRANSFORMERS_AVAILABLE:
    try:
        # Prefer local model path when present to avoid slow/blocked HF downloads.
        codebert_model_name = CODEBERT_MODEL_PATH if os.path.isdir(CODEBERT_MODEL_PATH) else "microsoft/codebert-base"
        if USE_FINETUNED_MODELS and os.path.isdir(CODEBERT_MODEL_PATH):
            codebert_model_name = CODEBERT_MODEL_PATH
        print(f"Loading CodeBERT ({codebert_model_name})...")
        codebert_tokenizer = AutoTokenizer.from_pretrained(codebert_model_name)
        codebert_model = AutoModel.from_pretrained(codebert_model_name)
        codebert_model = codebert_model.to(device)
        print("✓ CodeBERT loaded successfully")

        if HF_SPACE_URL:
            print(f"✓ Remote HF Space configured: {HF_SPACE_URL}")
        # Question generation via Ollama Qwen 2.5 7B
        if OLLAMA_AVAILABLE:
            print("✓ Qwen 2.5 7B via Ollama ready for question generation")
        else:
            print("⚠️ Ollama not available — question generation will use rule-based fallback")

        MODELS_LOADED = True
        print(f"\n✓ All models loaded on device: {device.upper()}\n")

    except KeyboardInterrupt:
        print("⚠️ Model loading interrupted")
        MODELS_LOADED = False
    except Exception as e:
        print(f"⚠️ Could not load models: {e}")
        MODELS_LOADED = False
else:
    print("⚠️ Torch/Transformers not available - models will not be loaded")

qwen_pipeline = None
_qwen_load_attempted = False


def _try_load_qwen_lora():
    """
    Lazy-load Qwen + LoRA adapter for question generation.
    Safe no-op when dependencies/model files are unavailable.
    Skips on CPU — 1.5B model is too slow for real-time generation.
    """
    global qwen_pipeline, _qwen_load_attempted

    if _qwen_load_attempted:
        return qwen_pipeline is not None
    _qwen_load_attempted = True

    if not USE_QWEN_LORA:
        return False
    if not (TORCH_AVAILABLE and TRANSFORMERS_AVAILABLE):
        return False
    if not os.path.isdir(QWEN_LORA_PATH):
        print(f"Qwen LoRA path not found: {QWEN_LORA_PATH}")
        return False
    if device == "cpu":
        print("⚠️ Skipping Qwen LoRA on CPU (too slow). Using Ollama Qwen instead.")
        return False

    try:
        from peft import PeftModel
        from transformers import AutoModelForCausalLM

        qwen_tokenizer = AutoTokenizer.from_pretrained(QWEN_BASE_MODEL, trust_remote_code=True)
        if qwen_tokenizer.pad_token is None:
            qwen_tokenizer.pad_token = qwen_tokenizer.eos_token

        model_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        qwen_base = AutoModelForCausalLM.from_pretrained(
            QWEN_BASE_MODEL,
            torch_dtype=model_dtype,
            low_cpu_mem_usage=True,
            trust_remote_code=True
        )
        qwen_model = PeftModel.from_pretrained(qwen_base, QWEN_LORA_PATH)
        qwen_model = qwen_model.to(device)

        qwen_pipeline = pipeline(
            "text-generation",
            model=qwen_model,
            tokenizer=qwen_tokenizer,
            device=0 if torch.cuda.is_available() else -1
        )
        print("Qwen LoRA loaded successfully")
        return True
    except Exception as e:
        print(f"Could not load Qwen LoRA: {str(e)[:200]}")
        qwen_pipeline = None
        return False


def _generate_with_qwen_lora(text, subject, num_questions):
    """
    Ask Qwen LoRA to emit strict JSON question objects matching backend schema.
    Uses the ChatML prompt format the model was fine-tuned on.
    """
    if not _try_load_qwen_lora():
        return None

    task_types = []
    for i in range(num_questions):
        if i % 3 == 0:
            task_types.append("mcq")
        elif i % 3 == 1:
            task_types.append("short")
        else:
            task_types.append("long")

    all_questions = []
    for task_type in task_types:
        difficulty = ["easy", "medium", "hard"][len(all_questions) % 3]
        prompt = (
            f"<|user|>\n"
            f"You are a Smart Exam System.\n"
            f"Subject: {subject}\n"
            f"Task Type: {task_type}\n"
            f"Difficulty: {difficulty}\n"
            f"Return STRICT JSON only.\n"
            f"Material:\n{text[:2000]}\n"
            f"<|assistant|>\n"
        )

        try:
            outputs = qwen_pipeline(
                prompt,
                max_new_tokens=350,
                do_sample=False,
                num_return_sequences=1,
            )
            raw = outputs[0]["generated_text"]
            if "<|assistant|>" in raw:
                raw = raw.split("<|assistant|>")[-1].strip()

            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end <= start:
                continue
            parsed = json.loads(raw[start:end + 1])
            if not isinstance(parsed, dict):
                continue

            q_text = str(parsed.get("question") or "").strip()
            if not q_text:
                continue

            if task_type == "mcq":
                options_raw = parsed.get("options", [])
                options_dict = {}
                if isinstance(options_raw, list):
                    for oi, opt in enumerate(options_raw[:4]):
                        options_dict[chr(65 + oi)] = str(opt)
                elif isinstance(options_raw, dict):
                    options_dict = options_raw
                correct = str(parsed.get("correct_option") or "A").strip().upper()
                all_questions.append({
                    "question_id": f"q_{subject}_{len(all_questions)}_qwen",
                    "question_text": q_text,
                    "question_type": "MCQ",
                    "difficulty": difficulty,
                    "marks": 1,
                    "options": options_dict if len(options_dict) >= 2 else {"A": "True", "B": "False"},
                    "correct_answer": correct if correct in options_dict else "A",
                    "model_used": "Qwen-LoRA",
                })
            else:
                all_questions.append({
                    "question_id": f"q_{subject}_{len(all_questions)}_qwen",
                    "question_text": q_text,
                    "question_type": "Long Answer",
                    "difficulty": difficulty,
                    "marks": 5,
                    "options": None,
                    "correct_answer": None,
                    "model_answer": str(parsed.get("answer") or "")[:500],
                    "model_used": "Qwen-LoRA",
                })
        except Exception as e:
            print(f"Qwen LoRA generation error (item {len(all_questions)}): {str(e)[:200]}")
            continue

    return all_questions if all_questions else None


def get_generation_model_status():
    """Lightweight status for health/diagnostics endpoints."""
    qwen_adapter_present = os.path.isdir(QWEN_LORA_PATH)
    return {
        "use_qwen_lora": USE_QWEN_LORA,
        "qwen_base_model": QWEN_BASE_MODEL,
        "qwen_lora_path": QWEN_LORA_PATH,
        "qwen_lora_adapter_present": qwen_adapter_present,
        "qwen_pipeline_loaded": qwen_pipeline is not None,
        "qwen_load_attempted": _qwen_load_attempted,
        "codebert_loaded": MODELS_LOADED,
        "ollama_available": OLLAMA_AVAILABLE,
        "ollama_model": "llama3.2:3b-instruct-q5_K_M",
        "device": device
    }


def detect_programming_language(text):
    """Detect programming language from code snippets"""
    language_patterns = {
        'Python': r'(def\s+\w+|import\s+\w+|from\s+\w+\s+import|if\s+__name__|\.py)',
        'Java': r'(public\s+class|import\s+java|\.java|System\.out\.println)',
        'C': r'(#include\s*[<"]|int\s+main|\.c\b|printf|void\s+)',
        'C++': r'(#include\s*[<"]|std::|using\s+namespace|\.cpp|cout)',
        'JavaScript': r'(function\s+\w+|const\s+\w+|let\s+\w+|\.js|console\.log)',
        'SQL': r'(SELECT|INSERT|UPDATE|DELETE|WHERE|FROM|JOIN|\.sql)',
        'HTML': r'(<html|<body|<div|<p>|<!DOCTYPE)',
        'CSS': r'(\.class\s*{|#id\s*{|@media|px;|color:)',
    }
    for lang, pattern in language_patterns.items():
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            return lang
    return None


def analyze_code_with_codebert(code_snippet):
    """Use CodeBERT to analyze code and generate insights"""
    try:
        if not MODELS_LOADED or codebert_model is None or not TORCH_AVAILABLE:
            return None
        inputs = codebert_tokenizer(code_snippet, return_tensors="pt", max_length=512, truncation=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = codebert_model(**inputs)
            embeddings = outputs.last_hidden_state
        return {
            'embedding_shape': embeddings.shape,
            'code_length': len(code_snippet),
            'tokens': inputs['input_ids'].shape[1],
            'embedding': embeddings.cpu().numpy()
        }
    except Exception as e:
        print(f"CodeBERT analysis error: {e}")
        return None


def extract_code_functions_and_concepts(text):
    """Extract functions, classes, and key concepts from code"""
    concepts = {
        'functions': re.findall(r'(?:def|function|public|void)\s+(\w+)\s*\(', text),
        'classes': re.findall(r'(?:class|interface)\s+(\w+)', text),
        'variables': re.findall(r'(?:int|float|string|var|let|const)\s+(\w+)\s*[=;]', text),
        'imports': re.findall(r'(?:import|from|#include)\s+["\']?(\w+)', text),
        'keywords': re.findall(r'\b(if|for|while|switch|try|catch|return|void|int|string|boolean)\b', text),
    }
    return {k: v for k, v in concepts.items() if v}


def detect_code_content(text):
    """Detect if text contains code snippets"""
    code_patterns = [
        r'def\s+\w+\s*\(',
        r'class\s+\w+\s*[:({]',
        r'for\s+\w+\s+in\s+',
        r'if\s+.*:',
        r'import\s+\w+',
        r'<\w+[^>]*>',
        r'SELECT|INSERT|UPDATE|DELETE',
        r'public\s+\w+',
        r'function\s+\w+',
        r'console\.log',
        r'System\.out\.println',
    ]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in code_patterns)


def generate_with_ollama(text, question_type="mcq", subject="general"):
    """Generate questions using Ollama Qwen 2.5 7B.
    Returns parsed dict or None."""
    if not OLLAMA_AVAILABLE or _ollama_generate is None:
        return None
    try:
        result = _ollama_generate(text[:1200], question_type, subject)
        if result and isinstance(result, dict):
            q_text = result.get("question", "").strip()
            if q_text and not _is_garbage_text(q_text):
                return result
        return None
    except Exception as e:
        print(f"Ollama Qwen generation error: {e}")
        return None


def _is_garbage_text(text):
    """Detect degenerate model output (repetitions, gibberish, etc.)."""
    if not text or len(text.strip()) < 5:
        return True
    t = text.strip().lower()
    words = t.split()
    if len(words) >= 4:
        counts = Counter(words)
        most_common_count = counts.most_common(1)[0][1]
        if most_common_count / len(words) > 0.6:
            return True
    unique = set(words)
    if len(words) > 6 and len(unique) <= 2:
        return True
    return False


_NOISE_CHARS_RE = re.compile(r'[\u2022\u2023\u25aa\u25ab\u25cf\u25cb\u25e6\u00a0\ufffd\uf075\*▪●•◦]')
_NONPRINT_RE    = re.compile(r'[\u0000-\u001f]')
_MCQ_START_RE   = re.compile(r'^(which|what|select|identify|choose)\b', re.IGNORECASE)
_SUBJECTIVE_BAD_START = re.compile(
    r'^(which\s+of\s+the\s+following|select|identify|choose)\b',
    re.IGNORECASE
)

# ── Topic validation & subject topic banks ────────────────────────────

def _is_valid_topic(topic):
    """Return True only if *topic* is clean enough to appear in a question stem."""
    if not topic or len(topic.strip()) < 4:
        return False
    t = topic.strip()
    # Code symbols or brackets
    if re.search(r'[><=(){\[\]$@#%^&;\\|/]', t):
        return False
    # CamelCase / run-together PDF artifacts (e.g. "RESEARCHSchID", "NameResID")
    if re.search(r'[a-z][A-Z]', t):
        return False
    # ALL-CAPS fragments longer than one word
    if len(t.split()) >= 2 and t == t.upper():
        return False
    # Dangling last word
    last_word = t.split()[-1].lower().rstrip('.,;:')
    _DANGLE = {'a','an','the','in','on','at','by','to','of','for','with','from',
               'and','or','but','is','are','was','were','has','have','had','new',
               'into','its','their','those','these','not','no','any','all','each',
               'such','some','than','about','that','which','between'}
    if last_word in _DANGLE:
        return False
    # Starts with pronoun / article
    first_word = t.split()[0].lower()
    _BAD_STARTS = {'it','this','that','they','he','she','we','you','there','here',
                   'no','any','when','while','where','if','although','because',
                   'once','so','yet','nor','but','and','or','however','furthermore'}
    if first_word in _BAD_STARTS:
        return False
    # Contains unbalanced quotes or stray parentheses
    if t.count('"') % 2 != 0 or t.count("'") > 2 or ')' in t or '(' in t:
        return False
    # Digit-heavy junk ("4SCHOLAR RESEARCHSchID")
    digit_ratio = sum(1 for c in t if c.isdigit()) / max(1, len(t))
    if digit_ratio > 0.15:
        return False
    # Too many words (shouldn't be a full sentence)
    if len(t.split()) > 7:
        return False
    return True


# ── Cross-subject keyword filter ────────────────────────────────────
# Keywords that strongly indicate a SPECIFIC subject.  When the target
# subject is different we reject topics / concepts containing them.
_SUBJECT_EXCLUSIVE_KW = {
    'database_fundamentals': [
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
    'python_programming': [
        'python', 'pip install', '__init__', 'virtualenv',
        'list comprehension', 'decorator', 'generator function',
    ],
    'object_oriented_programming': [
        'encapsulation', 'polymorphism', 'method overriding',
        'method overloading', 'abstract class', 'constructor overloading',
        'interface segregation',
    ],
    'web_development': [
        'html', 'css', 'javascript', 'dom manipulation', 'ajax',
        'rest api', 'http protocol', 'web server', 'responsive design',
    ],
    'software_engineering': [
        'requirements engineering', 'software testing', 'agile methodology',
        'waterfall model', 'scrum sprint', 'use case diagram',
        'risk management', 'configuration management', 'regression testing',
    ],
}


# Map short pool keys → full _SUBJECT_EXCLUSIVE_KW keys (and vice versa)
_SUBJECT_ALIASES = {
    'database': 'database_fundamentals',
    'db': 'database_fundamentals',
    'se': 'software_engineering',
    'python': 'python_programming',
    'oop': 'object_oriented_programming',
    'web': 'web_development',
}
# Also add reverse mappings so full keys resolve to themselves
for _full_key in list(_SUBJECT_EXCLUSIVE_KW.keys()):
    _SUBJECT_ALIASES[_full_key] = _full_key


def _is_on_topic(text, subject):
    """Return True only if *text* does NOT contain keywords exclusive to OTHER subjects."""
    if not text or not subject:
        return True
    # Normalize subject to match _SUBJECT_EXCLUSIVE_KW keys
    norm_subject = _SUBJECT_ALIASES.get(subject.lower(), subject)
    tl = text.lower()
    for other_subj, keywords in _SUBJECT_EXCLUSIVE_KW.items():
        if other_subj == norm_subject:
            continue
        for kw in keywords:
            if kw in tl:
                return False
    return True


_SUBJECT_TOPIC_BANKS = {
    'software_engineering': [
        'Requirements Engineering', 'Software Testing', 'Agile Development',
        'Waterfall Model', 'Risk Management', 'Software Maintenance',
        'Configuration Management', 'Code Refactoring', 'UML Diagrams',
        'Software Metrics', 'Version Control', 'Design Patterns',
        'Integration Testing', 'Continuous Integration', 'Use Case Modeling',
    ],
    'database_fundamentals': [
        'Normalization', 'SQL Joins', 'Primary Keys and Foreign Keys',
        'Entity-Relationship Model', 'Transaction Management', 'Indexing',
        'Concurrency Control', 'Data Independence', 'Relational Algebra',
        'Stored Procedures', 'Database Security', 'Query Optimization',
        'Database Schema Design', 'ACID Properties', 'Data Integrity Constraints',
    ],
    'python_programming': [
        'List Comprehensions', 'Exception Handling', 'Decorators',
        'Generator Functions', 'Modules and Packages', 'Lambda Functions',
        'File Handling in Python', 'Regular Expressions', 'Iterators',
        'Dictionary Operations', 'String Manipulation', 'Virtual Environments',
        'Inheritance in Python', 'Error Handling', 'Python Data Types',
    ],
    'object_oriented_programming': [
        'Encapsulation', 'Inheritance', 'Polymorphism', 'Abstraction',
        'Design Patterns', 'SOLID Principles', 'Constructor Overloading',
        'Method Overriding', 'Composition versus Inheritance',
        'Interface Segregation', 'Dependency Injection', 'Observer Pattern',
        'Factory Pattern', 'Single Responsibility Principle', 'Cohesion and Coupling',
    ],
    'web_development': [
        'DOM Manipulation', 'CSS Flexbox and Grid', 'RESTful API Design',
        'AJAX and Fetch Requests', 'Session Management', 'HTTP Protocol',
        'Responsive Web Design', 'Cross-Origin Resource Sharing', 'Web Accessibility',
        'Single-Page Applications', 'Server-Side Rendering', 'Web Security',
        'Form Validation', 'Cookie Management', 'WebSocket Communication',
    ],
    'general': [
        'Algorithm Analysis', 'Data Structures', 'System Design',
        'Security Principles', 'Performance Optimization', 'Modular Architecture',
        'Testing Strategies', 'Documentation Practices', 'Code Quality',
        'Project Management', 'Team Collaboration', 'Error Handling',
        'Resource Management', 'Scalability', 'Deployment Strategies',
    ],
}


def _clean_topic_phrase(topic):
    """Remove PDF artifacts: echoed/duplicate fragments, trailing noise."""
    if not topic:
        return topic
    words = topic.split()
    if len(words) >= 4:
        for split_pt in range(2, len(words)):
            left = ' '.join(words[:split_pt]).lower()
            right_first = words[split_pt].lower()
            if right_first in left.split() and right_first not in ('of', 'and', 'the', 'in', 'a', 'to', 'for', 'with'):
                candidate = ' '.join(words[:split_pt])
                if len(candidate) >= 4:
                    return candidate
    return topic


_TOPIC_BAD_TAIL = {
    "same", "etc", "note", "overview", "summary", "topic",
}


_DB_TOPIC_KEYWORDS = {
    "db_basics": ["database", "dbms", "data model", "schema", "instance"],
    "db_environment": ["file processing", "redundancy", "inconsistency", "program-data", "manual system"],
    "architecture": ["1-tier", "2-tier", "3-tier", "client-server", "application server"],
    "relational_model": ["relation", "tuple", "attribute", "domain", "relational model"],
    "keys": ["primary key", "foreign key", "candidate key", "composite key", "super key"],
    "er_model": ["entity", "relationship", "er model", "er diagram", "multivalued attribute", "derived attribute"],
    "views_constraints": ["view", "entity integrity", "referential integrity", "domain integrity", "constraint"],
    "normalization": ["normalization", "1nf", "2nf", "3nf", "anomaly", "functional dependency"],
    "relational_algebra": ["selection", "projection", "join", "union", "intersection", "difference", "relational algebra"],
}


def _detect_db_topics(text):
    tl = (text or "").lower()
    present = set()
    for topic, kws in _DB_TOPIC_KEYWORDS.items():
        if any(k in tl for k in kws):
            present.add(topic)
    return present


_DB_MCQ_BANK = [
    {
        "topic": "db_basics",
        "question_text": "What is a database?",
        "options": {
            "A": "A random collection of unrelated files",
            "B": "A shared collection of related data",
            "C": "A programming language for web pages",
            "D": "A hardware device used for networking",
        },
        "correct_answer": "B",
    },
    {
        "topic": "db_basics",
        "question_text": "Which software is responsible for creating, maintaining, and controlling databases?",
        "options": {
            "A": "Assembler",
            "B": "DBMS",
            "C": "Linker",
            "D": "Spreadsheet editor",
        },
        "correct_answer": "B",
    },
    {
        "topic": "db_environment",
        "question_text": "Which is a major problem of traditional file processing systems?",
        "options": {
            "A": "Data redundancy and inconsistency",
            "B": "Automatic concurrency control",
            "C": "Strong centralized security policies",
            "D": "Built-in transaction rollback mechanisms",
        },
        "correct_answer": "A",
    },
    {
        "topic": "architecture",
        "question_text": "In which DBMS architecture does the user directly interact with the database system on the same machine?",
        "options": {
            "A": "1-Tier architecture",
            "B": "2-Tier architecture",
            "C": "3-Tier architecture",
            "D": "Distributed-only architecture",
        },
        "correct_answer": "A",
    },
    {
        "topic": "architecture",
        "question_text": "The 2-tier database architecture is commonly known as:",
        "options": {
            "A": "Pipe-and-filter model",
            "B": "Client-server model",
            "C": "Peer-only model",
            "D": "Monolithic compiler model",
        },
        "correct_answer": "B",
    },
    {
        "topic": "relational_model",
        "question_text": "In the relational model, a relation is best represented as:",
        "options": {
            "A": "A table with rows and columns",
            "B": "A directed graph of processes",
            "C": "A stack of records with no schema",
            "D": "A binary tree of indexes only",
        },
        "correct_answer": "A",
    },
    {
        "topic": "relational_model",
        "question_text": "A tuple in a relation represents:",
        "options": {
            "A": "A column",
            "B": "A row",
            "C": "A full database",
            "D": "A query optimizer rule",
        },
        "correct_answer": "B",
    },
    {
        "topic": "keys",
        "question_text": "Which key uniquely identifies each record in a relation?",
        "options": {
            "A": "Foreign key",
            "B": "Primary key",
            "C": "Partial dependency",
            "D": "Derived key",
        },
        "correct_answer": "B",
    },
    {
        "topic": "keys",
        "question_text": "A foreign key is primarily used to:",
        "options": {
            "A": "Enforce relationships between tables",
            "B": "Encrypt all sensitive data fields",
            "C": "Replace all candidate keys",
            "D": "Store complete table backups",
        },
        "correct_answer": "A",
    },
    {
        "topic": "er_model",
        "question_text": "The ER model is mainly used for:",
        "options": {
            "A": "Conceptual database design",
            "B": "Physical disk formatting",
            "C": "Compiler optimization",
            "D": "Packet routing",
        },
        "correct_answer": "A",
    },
    {
        "topic": "er_model",
        "question_text": "In an ER diagram, an entity is usually represented by:",
        "options": {
            "A": "Rectangle",
            "B": "Circle",
            "C": "Diamond",
            "D": "Arrow head",
        },
        "correct_answer": "A",
    },
    {
        "topic": "views_constraints",
        "question_text": "A database view is best described as:",
        "options": {
            "A": "A virtual table based on a query",
            "B": "A physically copied table with automatic sync",
            "C": "A server-side programming language",
            "D": "A transaction log archive",
        },
        "correct_answer": "A",
    },
    {
        "topic": "views_constraints",
        "style": "scenario",
        "question_text": "A student portal should let users see only selected columns from multiple joined tables without exposing base-table internals. What is the best database feature for this?",
        "options": {
            "A": "A view created from a query",
            "B": "A full physical duplicate of all base tables",
            "C": "A trigger that drops hidden columns",
            "D": "A backup restore job",
        },
        "correct_answer": "A",
    },
    {
        "topic": "views_constraints",
        "question_text": "Which integrity rule ensures primary key values are never NULL?",
        "options": {
            "A": "Entity integrity",
            "B": "Referential integrity",
            "C": "Domain integrity",
            "D": "Semantic caching integrity",
        },
        "correct_answer": "A",
    },
    {
        "topic": "normalization",
        "style": "scenario",
        "question_text": "A sales table stores customer and order details in one row, causing repeated customer data and frequent update anomalies. Which normalization technique should be applied first?",
        "options": {
            "A": "Normalization",
            "B": "Denormalization only",
            "C": "Remove all primary keys",
            "D": "Store records in plain text files",
        },
        "correct_answer": "A",
    },
    {
        "topic": "normalization",
        "question_text": "Normalization is mainly performed to:",
        "options": {
            "A": "Reduce redundancy and update anomalies",
            "B": "Increase data duplication for speed",
            "C": "Avoid using keys in relations",
            "D": "Convert all tables into files",
        },
        "correct_answer": "A",
    },
    {
        "topic": "relational_algebra",
        "question_text": "Which relational algebra operation returns selected rows based on a condition?",
        "options": {
            "A": "Projection",
            "B": "Selection",
            "C": "Union",
            "D": "Cartesian product",
        },
        "correct_answer": "B",
    },
]


_DB_SHORT_BANK = [
    {
        "topic": "db_basics",
        "question_text": "Define a Database Management System (DBMS).",
        "model_answer": "A DBMS is software that defines, stores, retrieves, and controls access to a database while enforcing security, integrity, and concurrency."
    },
    {
        "topic": "db_environment",
        "question_text": "State two disadvantages of file processing systems.",
        "model_answer": "Typical disadvantages are data redundancy/inconsistency and program-data dependence (plus weak centralized security and harder sharing)."
    },
    {
        "topic": "relational_model",
        "question_text": "Differentiate between schema and instance.",
        "model_answer": "Schema is the logical structure/design of the database; instance is the current data stored at a particular time."
    },
    {
        "topic": "keys",
        "question_text": "What is a foreign key? Give a simple example.",
        "model_answer": "A foreign key is an attribute in one table that references the primary key of another table, e.g., Orders(CustomerID) referencing Customers(CustomerID)."
    },
    {
        "topic": "normalization",
        "question_text": "What is normalization and why is it important?",
        "model_answer": "Normalization organizes relations into normal forms (1NF/2NF/3NF) to reduce redundancy and prevent update, insert, and delete anomalies."
    },
]


_DB_LONG_BANK = [
    {
        "topic": "architecture",
        "question_text": "Explain 1-tier, 2-tier, and 3-tier DBMS architectures with suitable diagrams or examples.",
        "model_answer": "A complete answer should define each tier, show client/application/database responsibilities, compare scalability/security/maintenance, and include one practical use-case per architecture."
    },
    {
        "topic": "er_model",
        "question_text": "Explain the ER model and its core components with one sample case study.",
        "model_answer": "Expected points: entities, attributes, relationships, cardinality/participation constraints, and a small case study mapped into an ER diagram."
    },
    {
        "topic": "normalization",
        "question_text": "Explain normalization (1NF, 2NF, 3NF) and discuss its benefits in database design.",
        "model_answer": "Strong answers define each normal form, show decomposition steps from an unnormalized relation, and connect results to reduced redundancy and anomaly prevention."
    },
]

_PY_TOPIC_KEYWORDS = {
    "basics": ["python", "syntax", "indentation", "variable", "data type"],
    "control_flow": ["if", "else", "for", "while", "loop"],
    "functions": ["function", "def", "parameter", "return", "argument"],
    "exceptions": ["exception", "try", "except", "finally", "error handling"],
    "collections": ["list", "tuple", "dictionary", "dict", "set", "key-value"],
    "decorators": ["decorator", "@staticmethod", "@classmethod", "@property"],
    "virtual_envs": ["virtual environment", "venv", "virtualenv", "pip", "requirements.txt"],
    "code_reading": ["def ", "return ", "print(", "input(", "class ", "import "],
    "oop_python": ["class", "object", "inheritance", "encapsulation", "method"],
    "modules_files": ["module", "package", "import", "file handling", "open("],
}

_PY_MCQ_BANK = [
    {"topic": "basics", "difficulty": "easy", "marks": 1, "question_text": "What is a key reason Python is considered beginner-friendly?", "options": {"A": "Readable syntax with minimal boilerplate", "B": "Mandatory pointer arithmetic in all programs", "C": "Compilation only to machine code before execution", "D": "No support for standard libraries"}, "correct_answer": "A"},
    {"topic": "control_flow", "difficulty": "easy", "marks": 1, "question_text": "Which statement is used for decision making in Python?", "options": {"A": "switch-case only", "B": "if-elif-else", "C": "goto", "D": "typedef"}, "correct_answer": "B"},
    {"topic": "control_flow", "style": "scenario", "difficulty": "medium", "marks": 1, "question_text": "A program must process each item in a list and stop when a negative value appears. Which construct is most suitable?", "options": {"A": "A loop with a break condition", "B": "A class decorator", "C": "A recursive import", "D": "A static HTML form"}, "correct_answer": "A"},
    {"topic": "functions", "difficulty": "medium", "marks": 1, "question_text": "What is the main benefit of defining functions in Python?", "options": {"A": "Code reuse and modularity", "B": "Disabling exception handling", "C": "Replacing all loops automatically", "D": "Removing the need for variables"}, "correct_answer": "A"},
    {"topic": "functions", "style": "code", "difficulty": "medium", "marks": 1, "question_text": "What does the following function return when called as add(2, 3)?\n\ndef add(a, b):\n    return a + b", "options": {"A": "5", "B": "\"23\"", "C": "None", "D": "An error because return cannot be used inside a function"}, "correct_answer": "A"},
    {"topic": "exceptions", "difficulty": "medium", "marks": 1, "question_text": "What is the purpose of a try-except block?", "options": {"A": "To handle runtime errors gracefully", "B": "To define class inheritance", "C": "To create SQL tables", "D": "To import modules faster"}, "correct_answer": "A"},
    {"topic": "collections", "difficulty": "medium", "marks": 1, "question_text": "Which statement about Python dictionaries is correct?", "options": {"A": "They store data as key-value pairs and support lookup by key", "B": "They keep items only in alphabetical order and cannot store numbers", "C": "They behave exactly like tuples and cannot be modified", "D": "They are used only for importing modules"}, "correct_answer": "A"},
    {"topic": "decorators", "difficulty": "medium", "marks": 1, "question_text": "What is the main purpose of a decorator in Python?", "options": {"A": "To add or modify the behavior of a function or method without rewriting it", "B": "To replace all loops in a program", "C": "To create a database table automatically", "D": "To convert every variable into a constant"}, "correct_answer": "A"},
    {"topic": "virtual_envs", "difficulty": "medium", "marks": 1, "question_text": "Why are virtual environments used in Python projects?", "options": {"A": "To isolate project dependencies from the global Python installation", "B": "To make every script run without Python being installed", "C": "To convert Python code into HTML automatically", "D": "To remove the need for package management tools such as pip"}, "correct_answer": "A"},
    {"topic": "modules_files", "difficulty": "medium", "marks": 1, "question_text": "Why are modules used in Python projects?", "options": {"A": "To organize code into reusable files", "B": "To avoid functions entirely", "C": "To force single-file architecture", "D": "To disable package management"}, "correct_answer": "A"},
    {"topic": "modules_files", "style": "scenario", "difficulty": "medium", "marks": 1, "question_text": "You need to store user feedback in a text file and read it later. Which Python capability is directly relevant?", "options": {"A": "File handling with open(), read(), and write()", "B": "Only lambda expressions", "C": "Only list slicing", "D": "Only class inheritance"}, "correct_answer": "A"},
    {"topic": "oop_python", "difficulty": "medium", "marks": 1, "question_text": "In Python OOP, an object is:", "options": {"A": "An instance of a class", "B": "A built-in loop keyword", "C": "A database relation", "D": "A browser rendering model"}, "correct_answer": "A"},
]

_PY_SHORT_BANK = [
    {"topic": "functions", "difficulty": "medium", "marks": 2, "question_text": "Define a function in Python with a simple example.", "model_answer": "A function is a reusable block defined with def. Example: def add(a, b): return a + b."},
    {"topic": "exceptions", "difficulty": "medium", "marks": 2, "question_text": "What is exception handling in Python and why is it important?", "model_answer": "Exception handling uses try/except to catch runtime errors and keep programs stable instead of crashing abruptly."},
    {"topic": "collections", "difficulty": "medium", "marks": 2, "question_text": "Differentiate between a list and a tuple in Python.", "model_answer": "A list is mutable and uses square brackets, while a tuple is immutable and uses parentheses."},
    {"topic": "oop_python", "difficulty": "medium", "marks": 2, "question_text": "Differentiate between a class and an object.", "model_answer": "A class is a blueprint; an object is an instance created from that class."},
    {"topic": "modules_files", "difficulty": "medium", "marks": 2, "question_text": "What is a Python module?", "model_answer": "A module is a Python file containing reusable functions, classes, and variables that can be imported."},
]

_PY_LONG_BANK = [
    {"topic": "oop_python", "difficulty": "hard", "marks": 4, "question_text": "Explain core OOP concepts in Python with examples (class, object, inheritance, encapsulation).", "model_answer": "A complete answer should define each concept and show short Python snippets demonstrating them."},
    {"topic": "exceptions", "difficulty": "hard", "marks": 4, "question_text": "Explain Python exception handling flow using try, except, else, and finally with one practical scenario.", "model_answer": "Expected points: control flow of each block and how it prevents abrupt program failure."},
    {"topic": "virtual_envs", "difficulty": "hard", "marks": 4, "question_text": "Discuss Python virtual environments and explain how they help manage dependencies in real projects. Include one practical example.", "model_answer": "A strong answer should define a virtual environment, explain dependency isolation, show a simple venv creation/activation flow, and connect it to project-specific package management."},
    {"topic": "code_reading", "difficulty": "hard", "marks": 4, "question_text": "Read the following code and explain what it does line by line. Then state the final output.\n\ndef square_items(values):\n    result = []\n    for item in values:\n        result.append(item * item)\n    return result\n\nprint(square_items([1, 2, 3]))", "model_answer": "The function iterates through the list, squares each item, stores results in a new list, returns it, and the printed output is [1, 4, 9]."},
]

_WEB_TOPIC_KEYWORDS = {
    "html_css": ["html", "css", "semantic", "selector", "responsive"],
    "javascript_dom": ["javascript", "dom", "event", "fetch", "ajax"],
    "http_rest": ["http", "rest", "api", "get", "post", "status code"],
    "frontend_backend": ["frontend", "backend", "client", "server"],
    "security_accessibility": ["xss", "csrf", "accessibility", "validation", "authentication"],
}

_WEB_MCQ_BANK = [
    {"topic": "html_css", "question_text": "What is the role of HTML in web development?", "options": {"A": "Defines structure of web pages", "B": "Handles database backups", "C": "Compiles Java bytecode", "D": "Creates operating system kernels"}, "correct_answer": "A"},
    {"topic": "html_css", "question_text": "Which CSS feature is most useful for responsive page layout?", "options": {"A": "Flexbox/Grid", "B": "SQL joins", "C": "Binary trees", "D": "Pointer casting"}, "correct_answer": "A"},
    {"topic": "javascript_dom", "question_text": "What does DOM manipulation allow a developer to do?", "options": {"A": "Update page content dynamically", "B": "Format hard disks", "C": "Train neural networks directly in SQL", "D": "Replace all HTTP requests with DNS"}, "correct_answer": "A"},
    {"topic": "javascript_dom", "style": "scenario", "question_text": "A submit button should show a confirmation message without reloading the page. Which approach is most appropriate?", "options": {"A": "JavaScript event handling on the DOM", "B": "Recompile backend framework", "C": "Change database primary key", "D": "Use only static CSS"}, "correct_answer": "A"},
    {"topic": "http_rest", "question_text": "In REST APIs, which method is typically used to create a resource?", "options": {"A": "POST", "B": "GET", "C": "HEAD", "D": "TRACE"}, "correct_answer": "A"},
    {"topic": "frontend_backend", "question_text": "In a web app, backend code is primarily responsible for:", "options": {"A": "Business logic and data access", "B": "Only choosing font sizes", "C": "Only browser animations", "D": "Only HTML tag coloring"}, "correct_answer": "A"},
    {"topic": "security_accessibility", "question_text": "What is the purpose of input validation on web forms?", "options": {"A": "Reduce invalid or malicious input", "B": "Increase page load time intentionally", "C": "Replace authentication", "D": "Disable HTTPS"}, "correct_answer": "A"},
]

_WEB_SHORT_BANK = [
    {"topic": "html_css", "question_text": "Differentiate between HTML and CSS.", "model_answer": "HTML structures content, while CSS controls presentation and layout."},
    {"topic": "javascript_dom", "question_text": "What is the DOM?", "model_answer": "The DOM is a tree-like representation of a webpage that JavaScript can read and modify."},
    {"topic": "http_rest", "question_text": "What is a REST API?", "model_answer": "A REST API exposes resources over HTTP using standard methods like GET, POST, PUT, and DELETE."},
    {"topic": "security_accessibility", "question_text": "State two common web security concerns.", "model_answer": "Common concerns include XSS, CSRF, SQL injection, and weak authentication."},
]

_WEB_LONG_BANK = [
    {"topic": "frontend_backend", "question_text": "Explain frontend-backend interaction in a modern web application with one example flow.", "model_answer": "Expected points: client request, API endpoint, server processing, database interaction, and response rendering."},
    {"topic": "javascript_dom", "question_text": "Explain how JavaScript events and DOM updates are used to build interactive interfaces.", "model_answer": "Strong answers include event listeners, handlers, dynamic element updates, and practical UI examples."},
]

_SE_TOPIC_KEYWORDS = {
    "requirements": ["requirement", "srs", "functional requirement", "non-functional"],
    "sdlc_models": ["sdlc", "waterfall", "spiral", "incremental", "prototype"],
    "agile": ["agile", "scrum", "sprint", "product backlog", "standup"],
    "testing": ["testing", "unit test", "integration test", "regression", "verification", "validation"],
    "maintenance_config": ["maintenance", "configuration management", "version control", "change management"],
}

_SE_MCQ_BANK = [
    {"topic": "requirements", "question_text": "What is the primary goal of requirements engineering?", "options": {"A": "Capture and analyze stakeholder needs", "B": "Choose server hardware only", "C": "Write source code without planning", "D": "Skip validation"}, "correct_answer": "A"},
    {"topic": "sdlc_models", "question_text": "Which SDLC model follows a strict sequential phase-by-phase flow?", "options": {"A": "Waterfall model", "B": "Scrum only", "C": "Ad-hoc coding", "D": "No-process model"}, "correct_answer": "A"},
    {"topic": "agile", "question_text": "In Scrum, a sprint is:", "options": {"A": "A time-boxed development iteration", "B": "A single database query", "C": "A UML notation style", "D": "A deployment server"}, "correct_answer": "A"},
    {"topic": "agile", "style": "scenario", "question_text": "A team receives frequent changing requirements from users. Which process approach is most suitable?", "options": {"A": "Agile iterative development", "B": "Freeze requirements forever", "C": "Skip user feedback", "D": "Only manual paperwork"}, "correct_answer": "A"},
    {"topic": "testing", "question_text": "What is the main purpose of regression testing?", "options": {"A": "Ensure new changes do not break existing functionality", "B": "Replace all unit tests with UI tests", "C": "Measure internet bandwidth", "D": "Generate database schemas automatically"}, "correct_answer": "A"},
    {"topic": "maintenance_config", "question_text": "Configuration management mainly helps with:", "options": {"A": "Tracking and controlling software changes", "B": "Eliminating all documentation", "C": "Removing need for version control", "D": "Disabling testing"}, "correct_answer": "A"},
]

_SE_SHORT_BANK = [
    {"topic": "requirements", "question_text": "Differentiate between functional and non-functional requirements.", "model_answer": "Functional requirements define what the system should do; non-functional define quality constraints like performance or security."},
    {"topic": "agile", "question_text": "What is Scrum and why is it used?", "model_answer": "Scrum is an Agile framework using short sprints, backlog prioritization, and continuous feedback for iterative delivery."},
    {"topic": "testing", "question_text": "Define verification and validation.", "model_answer": "Verification checks if the product is built correctly; validation checks if the right product is built."},
]

_SE_LONG_BANK = [
    {"topic": "sdlc_models", "question_text": "Compare Waterfall and Agile models with suitable use cases.", "model_answer": "A complete answer should compare flexibility, risk handling, customer feedback cycle, and delivery pattern."},
    {"topic": "testing", "question_text": "Explain software testing levels (unit, integration, system, acceptance) with examples.", "model_answer": "Expected points: objective of each level and one practical example per level."},
]

_OOP_TOPIC_KEYWORDS = {
    "pillars": ["encapsulation", "inheritance", "polymorphism", "abstraction"],
    "class_object": ["class", "object", "constructor", "method", "attribute"],
    "relationships": ["association", "aggregation", "composition"],
    "overriding_binding": ["overriding", "overloading", "dynamic binding"],
    "solid_design": ["solid", "single responsibility", "open-closed", "design pattern"],
}

_OOP_MCQ_BANK = [
    {"topic": "class_object", "question_text": "In OOP, a class is best described as:", "options": {"A": "A blueprint for creating objects", "B": "A compiled executable file", "C": "A database transaction", "D": "A web protocol header"}, "correct_answer": "A"},
    {"topic": "class_object", "question_text": "An object in OOP is:", "options": {"A": "An instance of a class", "B": "A type of SQL index", "C": "A network port", "D": "A stylesheet rule"}, "correct_answer": "A"},
    {"topic": "pillars", "question_text": "Encapsulation primarily means:", "options": {"A": "Bundling data and methods with controlled access", "B": "Running multiple threads", "C": "Encrypting all files", "D": "Replacing inheritance with SQL joins"}, "correct_answer": "A"},
    {"topic": "pillars", "question_text": "Polymorphism allows:", "options": {"A": "One interface with multiple implementations", "B": "Only one class in a program", "C": "Eliminating methods", "D": "Direct hardware interrupts"}, "correct_answer": "A"},
    {"topic": "relationships", "style": "scenario", "question_text": "A Car object owns Engine objects, and Engine should not exist independently in that model. Which relationship fits best?", "options": {"A": "Composition", "B": "Aggregation", "C": "Association", "D": "Inheritance"}, "correct_answer": "A"},
    {"topic": "overriding_binding", "question_text": "Method overriding is used when:", "options": {"A": "A subclass provides its own implementation of a parent method", "B": "Two methods in same class share name but not parameters only", "C": "A variable is renamed", "D": "A constructor is removed"}, "correct_answer": "A"},
    {"topic": "solid_design", "question_text": "The Single Responsibility Principle states that a class should:", "options": {"A": "Have one clear responsibility", "B": "Handle all application layers", "C": "Never contain methods", "D": "Only store global variables"}, "correct_answer": "A"},
]

_OOP_SHORT_BANK = [
    {"topic": "pillars", "question_text": "Define abstraction with a simple example.", "model_answer": "Abstraction exposes essential behavior while hiding implementation details, e.g., using an interface to call a service."},
    {"topic": "overriding_binding", "question_text": "Differentiate between method overloading and method overriding.", "model_answer": "Overloading uses same method name with different signatures; overriding redefines inherited behavior in a subclass."},
    {"topic": "relationships", "question_text": "Differentiate between aggregation and composition.", "model_answer": "Aggregation is weak ownership; composition is strong ownership where part lifecycle depends on whole."},
]

_OOP_LONG_BANK = [
    {"topic": "pillars", "question_text": "Explain the four pillars of OOP with practical examples.", "model_answer": "Expected points: encapsulation, abstraction, inheritance, polymorphism and concrete examples of each."},
    {"topic": "solid_design", "question_text": "Explain SOLID principles and how they improve software maintainability.", "model_answer": "Strong answers define each principle and connect them to testability, extensibility, and reduced coupling."},
]

_CURATED_SUBJECT_CONFIG = {
    "python_programming": {
        "topic_keywords": _PY_TOPIC_KEYWORDS,
        "mcq_bank": _PY_MCQ_BANK,
        "short_bank": _PY_SHORT_BANK,
        "long_bank": _PY_LONG_BANK,
        "required_topics": {"functions", "exceptions", "collections"},
    },
    "web_development": {
        "topic_keywords": _WEB_TOPIC_KEYWORDS,
        "mcq_bank": _WEB_MCQ_BANK,
        "short_bank": _WEB_SHORT_BANK,
        "long_bank": _WEB_LONG_BANK,
        "required_topics": {"javascript_dom", "http_rest"},
    },
    "software_engineering": {
        "topic_keywords": _SE_TOPIC_KEYWORDS,
        "mcq_bank": _SE_MCQ_BANK,
        "short_bank": _SE_SHORT_BANK,
        "long_bank": _SE_LONG_BANK,
        "required_topics": {"requirements", "testing"},
    },
    "object_oriented_programming": {
        "topic_keywords": _OOP_TOPIC_KEYWORDS,
        "mcq_bank": _OOP_MCQ_BANK,
        "short_bank": _OOP_SHORT_BANK,
        "long_bank": _OOP_LONG_BANK,
        "required_topics": {"pillars", "class_object"},
    },
}


def _detect_topics_from_keywords(text, topic_keywords):
    tl = (text or "").lower()
    present = set()
    for topic, kws in (topic_keywords or {}).items():
        if any(k in tl for k in kws):
            present.add(topic)
    return present


def _ensure_curated_mcq_quality(selected_mcq, bank, present_topics, needed, required_topics):
    selected = list(selected_mcq)
    required_topics = set(required_topics or set())

    def _has_topic(topic):
        return any(item.get("topic") == topic for item in selected)

    def _inject(topic):
        candidates = [c for c in bank if c.get("topic") == topic]
        preferred = [c for c in candidates if c.get("topic") in present_topics]
        pool = preferred or candidates
        if not pool:
            return
        chosen = next((c for c in pool if all(c["question_text"] != s["question_text"] for s in selected)), pool[0])
        if len(selected) < needed:
            selected.append(chosen)
            return
        for i in range(len(selected) - 1, -1, -1):
            if selected[i].get("topic") not in required_topics:
                selected[i] = chosen
                return

    for topic in required_topics:
        if needed >= 4 and not _has_topic(topic):
            _inject(topic)

    if needed >= 4 and not any(item.get("style") == "scenario" for item in selected):
        scen = [c for c in bank if c.get("style") == "scenario"]
        if scen:
            chosen = scen[0]
            if len(selected) < needed:
                selected.append(chosen)
            else:
                selected[-1] = chosen

    deduped, seen = [], set()
    for item in selected:
        key = item.get("question_text", "").strip().lower()
        if key and key not in seen:
            deduped.append(item)
            seen.add(key)
    idx = 0
    while len(deduped) < needed and bank:
        cand = bank[idx % len(bank)]
        key = cand.get("question_text", "").strip().lower()
        if key and key not in seen:
            deduped.append(cand)
            seen.add(key)
        idx += 1
    return deduped[:needed]


def _generate_curated_subject_exam_pack(subject, text, num_questions):
    cfg = _CURATED_SUBJECT_CONFIG.get(subject)
    if not cfg:
        return []

    present = _detect_topics_from_keywords(text, cfg.get("topic_keywords"))
    if not present:
        present = set((cfg.get("topic_keywords") or {}).keys())

    num_mcq = max(1, round(num_questions * 0.6))
    num_short = max(1, round(num_questions * 0.25))
    num_long = num_questions - num_mcq - num_short
    if num_long < 0:
        num_long = 0
        num_short = num_questions - num_mcq

    selected_mcq = _pick_from_topic_bank(cfg["mcq_bank"], present, num_mcq)
    selected_mcq = _ensure_curated_mcq_quality(
        selected_mcq,
        cfg["mcq_bank"],
        present,
        num_mcq,
        cfg.get("required_topics"),
    )
    selected_short = _pick_from_topic_bank(cfg["short_bank"], present, num_short)
    selected_long = _pick_from_topic_bank(cfg["long_bank"], present, num_long)

    out = []
    for item in selected_mcq:
        shuffled_options, shuffled_correct = _shuffle_mcq_options(
            item["options"], item["correct_answer"]
        )
        out.append({
            "question_text": item["question_text"],
            "question_type": "MCQ",
            "difficulty": item.get("difficulty", "medium"),
            "marks": int(item.get("marks", 1)),
            "options": shuffled_options,
            "correct_answer": shuffled_correct,
            "model_answer": item.get("model_answer"),
            "model_used": f"Rule-based-{subject}-Coverage",
        })
    for item in selected_short:
        out.append({
            "question_text": item["question_text"],
            "question_type": "Short Answer",
            "difficulty": item.get("difficulty", "medium"),
            "marks": int(item.get("marks", 3)),
            "options": None,
            "correct_answer": None,
            "model_answer": item.get("model_answer"),
            "model_used": f"Rule-based-{subject}-Coverage",
        })
    for item in selected_long:
        out.append({
            "question_text": item["question_text"],
            "question_type": "Long Answer",
            "difficulty": item.get("difficulty", "hard"),
            "marks": int(item.get("marks", 5)),
            "options": None,
            "correct_answer": None,
            "model_answer": item.get("model_answer"),
            "model_used": f"Rule-based-{subject}-Coverage",
        })
    return out[:num_questions]


def _pick_from_topic_bank(bank, present_topics, needed):
    # First pass: prioritize questions whose topics are present in uploaded material.
    selected = []
    used_topics = set()
    for item in bank:
        if len(selected) >= needed:
            break
        if item["topic"] in present_topics and item["topic"] not in used_topics:
            selected.append(item)
            used_topics.add(item["topic"])
    # Second pass: fill remaining slots with unique-topic items.
    for item in bank:
        if len(selected) >= needed:
            break
        if item["topic"] not in used_topics:
            selected.append(item)
            used_topics.add(item["topic"])
    # Final pass: if still short, allow repeats.
    idx = 0
    while len(selected) < needed and bank:
        selected.append(bank[idx % len(bank)])
        idx += 1
    return selected


def _shuffle_mcq_options(options, correct_answer):
    """Randomize MCQ options and remap the correct answer key."""
    if not isinstance(options, dict) or not options:
        return options, (correct_answer or "A")

    ordered_items = [(k, options[k]) for k in sorted(options.keys())]
    if not ordered_items:
        return options, (correct_answer or "A")

    orig_correct = str(correct_answer or "").strip().upper()[:1]
    if orig_correct not in dict(ordered_items):
        orig_correct = ordered_items[0][0]

    rng = random.SystemRandom()
    rng.shuffle(ordered_items)

    new_options = {}
    new_correct = "A"
    for i, (old_key, value) in enumerate(ordered_items):
        label = chr(65 + i)
        new_options[label] = value
        if old_key == orig_correct:
            new_correct = label
    return new_options, new_correct


def _ensure_db_mcq_quality(selected_mcq, present_topics, needed):
    """Enforce DB MCQ quality constraints for better paper balance."""
    selected = list(selected_mcq)

    def _has(predicate):
        return any(predicate(item) for item in selected)

    def _pick_candidate(topic=None, style=None):
        candidates = _DB_MCQ_BANK
        if topic is not None:
            candidates = [c for c in candidates if c.get("topic") == topic]
        if style is not None:
            candidates = [c for c in candidates if c.get("style") == style]
        preferred = [c for c in candidates if c.get("topic") in present_topics]
        pool = preferred or candidates
        for cand in pool:
            if all(cand["question_text"] != s["question_text"] for s in selected):
                return cand
        return pool[0] if pool else None

    def _inject(candidate, protected_topics=None):
        if not candidate:
            return
        if len(selected) < needed:
            selected.append(candidate)
            return
        protected_topics = set(protected_topics or [])
        for i in range(len(selected) - 1, -1, -1):
            t = selected[i].get("topic")
            if t not in protected_topics:
                selected[i] = candidate
                return

    if needed >= 5 and not _has(lambda i: i.get("topic") == "normalization"):
        _inject(_pick_candidate(topic="normalization"), protected_topics={"views_constraints"})
    if needed >= 5 and not _has(lambda i: i.get("topic") == "views_constraints"):
        _inject(_pick_candidate(topic="views_constraints"), protected_topics={"normalization"})
    if needed >= 4 and not _has(lambda i: i.get("style") == "scenario"):
        _inject(
            _pick_candidate(style="scenario"),
            protected_topics={"normalization", "views_constraints"},
        )

    # Final dedup by question text and maintain target size.
    deduped = []
    seen = set()
    for item in selected:
        key = item.get("question_text", "").strip().lower()
        if key and key not in seen:
            deduped.append(item)
            seen.add(key)
    idx = 0
    while len(deduped) < needed and _DB_MCQ_BANK:
        cand = _DB_MCQ_BANK[idx % len(_DB_MCQ_BANK)]
        key = cand.get("question_text", "").strip().lower()
        if key and key not in seen:
            deduped.append(cand)
            seen.add(key)
        idx += 1
    return deduped[:needed]


def _generate_database_exam_pack(text, num_questions):
    """Generate higher-quality DB exam questions with explicit coverage."""
    present = _detect_db_topics(text)
    if not present:
        present = set(_DB_TOPIC_KEYWORDS.keys())

    num_mcq = max(1, round(num_questions * 0.6))
    num_short = max(1, round(num_questions * 0.25))
    num_long = num_questions - num_mcq - num_short
    if num_long < 0:
        num_long = 0
        num_short = num_questions - num_mcq

    selected_mcq = _pick_from_topic_bank(_DB_MCQ_BANK, present, num_mcq)
    selected_mcq = _ensure_db_mcq_quality(selected_mcq, present, num_mcq)
    selected_short = _pick_from_topic_bank(_DB_SHORT_BANK, present, num_short)
    selected_long = _pick_from_topic_bank(_DB_LONG_BANK, present, num_long)

    out = []
    for item in selected_mcq:
        shuffled_options, shuffled_correct = _shuffle_mcq_options(
            item["options"], item["correct_answer"]
        )
        out.append({
            "question_text": item["question_text"],
            "question_type": "MCQ",
            "difficulty": item.get("difficulty", "medium"),
            "marks": int(item.get("marks", 1)),
            "options": shuffled_options,
            "correct_answer": shuffled_correct,
            "model_answer": item.get("model_answer"),
            "model_used": "Rule-based-DB-Coverage",
        })
    for item in selected_short:
        out.append({
            "question_text": item["question_text"],
            "question_type": "Short Answer",
            "difficulty": item.get("difficulty", "medium"),
            "marks": int(item.get("marks", 3)),
            "options": None,
            "correct_answer": None,
            "model_answer": item.get("model_answer"),
            "model_used": "Rule-based-DB-Coverage",
        })
    for item in selected_long:
        out.append({
            "question_text": item["question_text"],
            "question_type": "Long Answer",
            "difficulty": item.get("difficulty", "hard"),
            "marks": int(item.get("marks", 5)),
            "options": None,
            "correct_answer": None,
            "model_answer": item.get("model_answer"),
            "model_used": "Rule-based-DB-Coverage",
        })
    return out[:num_questions]


def _sanitize_topic_label(topic, subject):
    """Normalize noisy extracted topics into concise exam-safe labels."""
    t = _clean_text_fragment(topic or "")
    if not t:
        return ""

    # Remove odd punctuation artifacts and repeated whitespace.
    t = re.sub(r"[\"'`]+", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()

    # Remove trailing junk token like "... Same".
    words = t.split()
    while words and words[-1].lower().rstrip(".,;:?!") in _TOPIC_BAD_TAIL:
        words.pop()
    t = " ".join(words).strip()

    # Canonical DB cleanup for common noisy fragments.
    t_low = t.lower()
    if "duplication of data" in t_low:
        t = "data duplication"

    # Fallback to subject bank when topic is unusable or off-topic.
    if (not t or len(t.split()) < 1 or not _is_valid_topic(t) or not _is_on_topic(t, subject)):
        bank = _SUBJECT_TOPIC_BANKS.get(subject, _SUBJECT_TOPIC_BANKS["general"])
        return bank[0]
    return t


def _canonical_topic_key(text):
    """Stable key for dedup/coverage checks."""
    t = _clean_text_fragment(text or "").lower()
    t = re.sub(r"[^a-z0-9\s]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    for pref in ("what is ", "which of the following ", "which statement ", "briefly explain ", "discuss "):
        if t.startswith(pref):
            t = t[len(pref):].strip()
    return t

def _pick_topic(sentences, idx, subject, concepts=None):
    """Extract a VALID topic from *sentences* for Short/Long stems.

    Priority: _extract_key_phrase → concept list → subject topic bank.
    Never returns garbage — always returns a clean, printable topic.
    Rejects topics that belong to a DIFFERENT subject (cross-subject filter).
    """
    # 1. Try current + up to 8 neighbouring sentences
    for offset in range(min(len(sentences), 9)):
        t = _extract_key_phrase(sentences[(idx + offset) % len(sentences)])
        if t and _is_valid_topic(t) and _is_on_topic(t, subject):
            return _sanitize_topic_label(_clean_topic_phrase(t), subject)

    # 2. Try concept list if available
    if concepts:
        for offset in range(min(len(concepts), 6)):
            c_name = concepts[(idx + offset) % len(concepts)][0]
            if c_name and _is_valid_topic(c_name) and _is_on_topic(c_name, subject):
                return _sanitize_topic_label(_clean_topic_phrase(c_name), subject)

    # 3. Subject topic bank (guaranteed clean + on-topic)
    bank = _SUBJECT_TOPIC_BANKS.get(subject, _SUBJECT_TOPIC_BANKS['general'])
    return _sanitize_topic_label(bank[idx % len(bank)], subject)


def _clean_text_fragment(text):
    t = str(text or "")
    t = _NOISE_CHARS_RE.sub(" ", t)
    t = _NONPRINT_RE.sub(" ", t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _sentence_case(text):
    t = _clean_text_fragment(text)
    if not t:
        return ""
    if t[0].islower():
        t = t[0].upper() + t[1:]
    if t[-1] not in ".!?":
        t += "."
    return t


def _is_complete_sentence(text, min_words=5):
    t = _clean_text_fragment(text)
    if not t:
        return False
    words = t.split()
    if len(words) < min_words:
        return False
    if words[-1].lower().rstrip(".,;:?!") in {
        "to", "for", "and", "or", "with", "of", "in", "on", "at", "from", "by",
        "the", "a", "an", "that", "which", "who", "whose", "this", "these", "those",
        "be", "been", "being", "not", "also", "only", "such", "as", "if", "but",
        "into", "than", "about", "their", "its", "so", "whether",
    }:
        return False
    return True


def _prepare_sentences(text):
    """Extract cleaner candidate sentences from noisy OCR/PDF text."""
    raw = _clean_text_fragment(text)
    if not raw:
        return []

    chunks = re.split(r'[\n\r]+|(?<=[.!?])\s+', raw)
    out = []
    seen = set()
    for c in chunks:
        c = _clean_text_fragment(c)
        if len(c) < 20:
            continue
        if c.lower().startswith(("slide ", "chapter ", "page ")):
            continue
        if c.count("?") > 1:
            continue
        key = re.sub(r'[^a-z0-9]+', ' ', c.lower()).strip()
        if len(key) < 18 or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _normalize_question_type(value):
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in ("mcq", "multiple_choice", "multiplechoice", "true_false", "truefalse"):
        return "MCQ"
    if raw in ("short_answer", "shortanswer"):
        return "Short Answer"
    if raw in ("long_answer", "longanswer", "essay", "code", "coding"):
        return "Long Answer"
    return "MCQ"


# Course/subject titles that must not appear as MCQ concept in stems
_QG_SUBJECT_TITLES = {
    'database fundamentals', 'database basics', 'database management',
    'database management system', 'database management systems', 'dbms', 'rdbms',
    'introduction to databases', 'introduction to dbms',
    'software engineering', 'software reengineering',
    'data structures', 'data structures and algorithms', 'algorithms',
    'operating systems', 'computer networks', 'computer science',
    'information technology', 'object oriented programming',
    'object-oriented programming', 'oop', 'python programming',
    'web development', 'machine learning', 'artificial intelligence',
    'general', 'the concept', 'concept', 'topic', 'subject',
    # Administrative / slide-heading terms
    'course learning outcomes', 'course contents', 'course outline',
    'course introduction', 'learning outcomes', 'learning objectives',
    'clo', 'plo', 'introduction', 'overview', 'summary',
    # Partial slide-heading fragment concepts
    'course learning', 'manual file', 'file based', 'file based approach',
    'manual file storage', 'manual file storage approach',
    'processing system', 'file processing system', 'file system',
}


def _build_mcq_stem(topic, idx, subject=None):
    """Build an MCQ question stem. Returns None when topic is too generic/course-title/off-topic."""
    tl = re.sub(r'\s+', ' ', (topic or '')).strip().lower()
    # Reject: empty, course/subject title, question-word-as-concept, >5 words, or single generic word
    if (not tl
            or tl in _QG_SUBJECT_TITLES
            or tl.split()[0] in ('what', 'how', 'why', 'which', 'who', 'when', 'where')
            or len(topic.strip().split()) > 5
            or len(topic.strip().split()) < 2):   # must be at least 2 words
        return None
    # Reject administrative / slide-heading concepts containing these terms
    _ADMIN_WORDS = {'clo', 'plo', 'outcome', 'objectives', 'contents', 'syllabus',
                   'schedule', 'grading', 'assessment', 'marks', 'exam', 'quiz'}
    if any(w in tl.split() for w in _ADMIN_WORDS):
        return None
    # Reject topics that belong to a DIFFERENT subject
    if subject is not None and not _is_on_topic(topic, subject):
        return None
    templates = [
        f"Which of the following correctly defines {topic}?",
        f"How is {topic} best characterised in this context?",
        f"What does {topic} primarily involve?",
        f"Which statement accurately describes {topic}?",
    ]
    return templates[idx % len(templates)]


def _sanitize_option_text(text):
    t = _clean_text_fragment(text)
    # Strip option-key prefixes like "A)" "B." "(C)" at the start
    t = re.sub(r'^[A-Da-d]\s*[\)\.\:]\s*', '', t).strip()
    # Strip fragment starts: leading ")" or text starting with a closing paren fragment
    t = re.sub(r'^[\)\]\}]+\s*', '', t).strip()
    # Strip "Word) " PDF fragment prefix: "Reports) Each program..." → "Each program..."
    t = re.sub(r'^[A-Za-z]{1,25}\)\s+', '', t).strip()
    # Strip "ConceptName is/are Definition" slide copypaste prefix.
    # E.g. "Meta Data is Database definition Data..." → "Database definition Data..."
    #      "Program data independence is Advantages..." → "Advantages..."
    # Keep options where the definition starts with a verb form ("defined","stored",etc.)
    # or an article ("a","an","the") -- these are already clean sentences.
    _xisy = re.match(
        r'^([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)+)\s+(?:is|are|refers?\s+to|means|denotes?|describes?)\s+(.{8,})$', t)
    if _xisy:
        _def = _xisy.group(2).strip()
        _def_first = _def.split()[0].lower() if _def.split() else ''
        _OK_FIRSTS = {
            'a', 'an', 'the', 'defined', 'stored', 'used', 'called', 'known',
            'referred', 'designed', 'implemented', 'created', 'based', 'applied',
            'achieved', 'performed', 'produced', 'modified', 'separated',
        }
        if _def_first not in _OK_FIRSTS:
            # If the remaining definition is too short, reject entirely
            if len(_def.split()) < 5:
                return ''
            # Likely raw slide copypaste — drop the concept prefix, keep definition
            t = _sentence_case(_def)
    # Strip incomplete trailing parenthetical like "(e.g." or "(e.g"
    t = re.sub(r'\s*\(e\.?g\.?[^)]*$', '', t, flags=re.I).strip()
    t = re.sub(r'\s*\(etc\.?\s*$', '', t, flags=re.I).strip()
    # Strip PDF single-letter truncation artifact: "...database s." → "...database"
    t = re.sub(r'\s+[a-z]\.$', '', t).strip()
    # Fix PDF run-together words (e.g. "ofdata" → "of data")
    t = re.sub(r'\bofdata\b', 'of data', t, flags=re.I)
    t = re.sub(r'\bofthe\b', 'of the', t, flags=re.I)
    t = re.sub(r'\binthe\b', 'in the', t, flags=re.I)
    t = re.sub(r'\bandthe\b', 'and the', t, flags=re.I)
    t = re.sub(r'\btheapplication\b', 'the application', t, flags=re.I)
    t = re.sub(r'\btheapplications\b', 'the applications', t, flags=re.I)
    t = re.sub(r'\bthedata\b', 'the data', t, flags=re.I)
    t = re.sub(r'\btheprogram\b', 'the program', t, flags=re.I)
    t = re.sub(r'\btheprograms\b', 'the programs', t, flags=re.I)
    t = re.sub(r'\bthedatabase\b', 'the database', t, flags=re.I)
    t = re.sub(r'\bthesystem\b', 'the system', t, flags=re.I)
    t = re.sub(r'\btheuser\b', 'the user', t, flags=re.I)
    t = re.sub(r'\bthefile\b', 'the file', t, flags=re.I)
    t = re.sub(r'\s{2,}', ' ', t).strip()
    # Fix space-hyphen PDF artifacts ("end -users" → "end-users")
    t = re.sub(r'(\w)\s+-(\w)', r'\1-\2', t)
    # Reject options that start with content-free fragment patterns
    _BAD_OPT_STARTERS = ('data that ', 'the data that ', 'this data that ')
    if any(t.lower().startswith(bs) for bs in _BAD_OPT_STARTERS):
        return ''
    # Truncate at 110 chars
    if len(t) > 110:
        cut = t[:110]
        t = cut[:cut.rfind(" ")] if " " in cut else cut
    # Post-truncation dangle-word check (truncation can create new dangles)
    _POST_DANGLE = {
        'a', 'an', 'the', 'that', 'which', 'who', 'whom', 'whose',
        'and', 'or', 'but', 'if', 'as', 'by', 'to', 'of', 'in',
        'on', 'at', 'for', 'with', 'from', 'into', 'than', 'about',
        'be', 'been', 'being', 'not', 'also', 'only', 'such',
        'its', 'their', 'so', 'whether',
    }
    _words = t.split()
    if _words and _words[-1].lower().rstrip('.,;:?!') in _POST_DANGLE:
        # Try trimming the dangle word to get a clean ending
        t = ' '.join(_words[:-1])
        # If still dangling or too short, reject entirely
        _words2 = t.split()
        if len(_words2) < 4 or (_words2 and _words2[-1].lower().rstrip('.,;:?!') in _POST_DANGLE):
            return ''
    out = _sentence_case(t)
    if not _is_realistic_option(out):
        return ""
    return out


_QG_LAST_RESORT = {
    'database': [
        "Storing all records in a single flat file without any access control layer",
        "Allowing all users to modify raw data directly without a database management system",
        "Duplicating every data record across multiple files to speed up retrieval operations",
    ],
    'python': [
        "Writing all program logic in a single file without any functions or modules",
        "Declaring variable types explicitly before every assignment in Python code",
        "Avoiding all exception handling and letting the program crash on every error",
    ],
    'oop': [
        "Making all class attributes public and accessible to every part of the program",
        "Avoiding inheritance entirely and copying all code manually between classes",
        "Treating all objects as simple data containers without any methods or behavior",
    ],
    'web': [
        "Requiring a full page reload for every single user interaction on the website",
        "Using only inline styles and avoiding all external CSS files for web page styling",
        "Processing all client-side logic on the server without any JavaScript execution",
    ],
    'se': [
        "Skipping all testing activities and deploying code directly to production",
        "Writing all requirements after the system has been fully coded and deployed",
        "Avoiding version control and managing all code changes through manual file copies",
    ],
    'generic': [
        "Performing all complex tasks manually without any systematic methodology or tools",
        "Avoiding all documentation and relying entirely on verbal communication for knowledge transfer",
        "Ignoring established best practices and implementing ad-hoc solutions for every problem",
    ],
}


_UNREALISTIC_OPTION_PATTERNS = [
    r"\braw machine code\b",
    r"\bwithout any (?:validation|security|management)\b",
    r"\ball users\b.*\bmodify raw data\b",
    r"\bduplicating every data record\b",
    r"\bplain text\b.*\bpassword",
]


def _is_realistic_option(text):
    """Reject absurd distractors that reduce exam quality."""
    t = (text or "").lower()
    if not t:
        return False
    for pat in _UNREALISTIC_OPTION_PATTERNS:
        if re.search(pat, t):
            return False
    return True


def _build_generic_distractors(topic, subject='generic'):
    # Subject-aware academic distractors — never include subject/course title as topic phrase
    tl = re.sub(r'\s+', ' ', (topic or '')).strip().lower()
    subj = subject if subject is not None else 'generic'
    if not tl or tl in _QG_SUBJECT_TITLES or len(tl.split()) <= 1:
        # Domain-safe last-resort fallbacks — subject-matched
        _subj_key = subj.lower() if subj else 'generic'
        # Map long subject names to pool keys
        for k in _QG_LAST_RESORT:
            if k in _subj_key:
                return list(_QG_LAST_RESORT[k])
        return list(_QG_LAST_RESORT['generic'])
    t = topic.strip()
    return [
        _sentence_case(f"A process that bypasses {t} and operates without any systematic controls"),
        _sentence_case(f"An older technique replaced by {t} due to lack of reliability and consistency"),
        _sentence_case(f"A manual workaround that does not leverage the benefits provided by {t}"),
    ]


def _repair_subjective_stem(q_type, topic):
    if q_type == "Short Answer":
        return f"Briefly explain {topic} in 2-3 lines."
    return f"Discuss {topic} in detail with one practical example."


# ═══════════════════════════════════════════════════════════════════════════════
#  FIX 1 — _extract_key_phrase (REWRITTEN)
# ═══════════════════════════════════════════════════════════════════════════════

_KP_SLIDE_PFXS = re.compile(
    r'^(?:Reengineering\s+concepts|General\s+Idea|Code\s+Reverse\s+Engineering|'
    r'GENERAL\s+MODEL\s+FOR\s+SOFTWARE(?:\s+REENGINEERING)?|'
    r'REENGINEERING\s+PROCESS|TECHNIQUES\s+USED\s+FOR\s+REVERSE\s+ENGINEERING|'
    r'Slide\s+\d+|Chapter\s+\d+|Section\s+\d+)\s+',
    re.I
)
_KP_GERUND = re.compile(r'^[A-Z][a-z]+ing\s')   # "Understanding…", "Answering…"
# Single-word concepts that are too generic to be useful MCQ topics
_SUPER_GENERIC_NOUNS = {
    'collection', 'data', 'system', 'process', 'file', 'storage', 'users',
    'information', 'approach', 'method', 'type', 'types', 'records', 'fields',
    'value', 'values', 'table', 'tables', 'attribute', 'attributes', 'user',
    'concept', 'item', 'thing', 'point', 'area', 'field', 'overview',
    'summary', 'introduction', 'analysis', 'review', 'figure', 'diagram',
    'feature', 'features', 'property', 'properties', 'element', 'elements',
}

_KP_BAD_FIRST = {
    # conjunctions / prepositions
    'on','in','at','by','to','of','for','with','from','and','or','but','if','as',
    # articles / pronouns
    'the','a','an','this','these','those','it','its','they','their',
    # question/interrogative words — prevent "What", "How" being extracted as concepts
    'what','how','why','who','whom','whose',
    # adverbs that signal non-concept sentence starts
    'fundamentally','generally','basically','typically','specifically','primarily',
    'additionally','furthermore','however','therefore','thus','hence',
    'there','here','note','see','also','moreover','consequently',
    'several','various','certain','once','some','which','that',
    'when','where','while','although','since','unless',
    'never','always','often','usually','normally','perhaps',
    # gerunds that are not concept names
    'understanding','answering','focusing','hiding','making','finding',
    'performing','following','comparing','removing','creating','enabling',
}


def _extract_key_phrase(sentence):
    """
    Extract a clean concept name from a sentence for use in question stems.

    Recognises two universal patterns that appear across all subjects:
      • "ConceptName: definition text"  (e.g. "Stack: A LIFO data structure…")
      • "X is / are / means / concerns Y"  (e.g. "SQL is a language for…")

    Returns '' when no clean concept is found; callers already handle this:
        `_extract_key_phrase(s) or subject.replace('_', ' ')`
    so the empty string is a safe sentinel — no caller changes needed.

    Works across: software_engineering, data_structures, database_systems,
    operating_systems, object_oriented_programming, python_programming,
    web_development, algorithms, machine_learning, general.
    """
    s = re.sub(
        r'[\u2022\u2023\u25aa\u25ab\u25cf\u25cb\u25e6\u00a0\ufffd\uf075\*▪●•◦]',
        '', str(sentence or ""))
    s = re.sub(r'[\u0000-\u001f]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()

    # Strip slide-header prefixes glued to the start
    # e.g. "Reengineering concepts  A good comprehension…" → strip prefix
    s = _KP_SLIDE_PFXS.sub('', s).strip()

    # ── Pattern 1: "ConceptName: definition text" ──────────────────────────
    m = re.match(r'^([A-Z][a-zA-Z0-9\s\(\)\.]{1,45}?):\s+\S', s)
    if m:
        c = m.group(1).strip()
        words = c.split()
        first = words[0].lower() if words else ''
        if (1 <= len(words) <= 5
                and len(c) >= 2
                and not _KP_GERUND.match(c)
                and first not in _KP_BAD_FIRST
                # Reject single non-acronym words (e.g. "Collection", "Data")
                and not (len(words) == 1 and c != c.upper())
                # Reject super-generic single-noun concepts
                and not (len(words) == 1 and c.lower() in _SUPER_GENERIC_NOUNS)
                # Reject broken fragments ending with bare function words
                and not c.lower().endswith((' that', ' which', ' and', ' or'))):
            return c

    # ── Pattern 2: "X is / are / means / concerns Y" ──────────────────────
    m = re.match(
        r'^(.{2,50}?)\s+(?:is|are|refers?\s+to|means?|concerns?|enables?)\s+\S',
        s, re.I)
    if m:
        c = m.group(1).strip().rstrip('.,;()')
        # Strip trailing relative-clause starters ("Constructing a database which" → "Constructing a database")
        c = re.sub(r'\s+(?:which|that|who|whose|where|when)$', '', c, flags=re.I).strip()
        words = c.split()
        first = words[0].lower() if words else ''
        if (1 <= len(words) <= 5
                and len(c) >= 2
                and not _KP_GERUND.match(c)
                and first not in _KP_BAD_FIRST
                # Reject single non-acronym words (e.g. "Collection", "Data")
                and not (len(words) == 1 and c != c.upper())
                # Reject super-generic single-noun concepts
                and not (len(words) == 1 and c.lower() in _SUPER_GENERIC_NOUNS)
                # Reject broken fragments ending with bare function words
                and not c.lower().endswith((' that', ' which', ' and', ' or'))):
            return c

    return ''   # safe — callers: `_extract_key_phrase(s) or subject.replace('_',' ')`


# ═══════════════════════════════════════════════════════════════════════════════
#  FIX 2 — PDF line-join + concept extraction helpers (NEW)
# ═══════════════════════════════════════════════════════════════════════════════

_WRAP_SLIDE_STRIP = re.compile(
    r'^(?:Reengineering\s+concepts|General\s+Idea|Code\s+Reverse\s+Engineering)\s+',
    re.I
)
_WRAP_ALLCAPS = re.compile(r'^[A-Z][A-Z\s\-/\']{5,}$')
_WRAP_CONT_WORDS = {
    'it','and','or','by','to','of','in','is','are','was','were','the','a','an',
    'at','for','with','from','into','increased','decreased','produced','performed',
    'achieved','documentation','characteristics','alteration','does','not',
    'modification','toward','engineering','generally','perhaps','usually',
    'normally','another','therefore','thus','besides','however','although',
    'whereas','while','on','namely','such','each',
}


def _join_wrapped_lines(text):
    """
    Join PDF continuation lines so _prepare_sentences() receives whole sentences.

    A line is treated as a continuation of the previous when it:
      • starts with a lowercase letter, OR
      • starts with a known continuation word (it, and, by, to, of, …)

    Never joins bullet lines or numbered list items — those must stay separate.
    Domain-agnostic: works for any subject without hardcoded vocabulary.
    """
    lines = text.split('\n')
    joined = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        # Drop pure ALL-CAPS slide headers (e.g. "GENERAL MODEL FOR SOFTWARE REENGINEERING")
        if _WRAP_ALLCAPS.match(stripped) and len(stripped.split()) <= 6:
            i += 1
            continue

        # Join continuation lines
        while i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if not nxt:
                break
            # Never join numbered/lettered list items
            if re.match(r'^\([ivxlc\d]+\)', nxt.lower()):
                break
            if re.match(r'^[ivxIVX]{1,4}\.', nxt):
                break
            if re.match(r'^\d+\.', nxt):
                break
            # Never join bullet lines
            if re.match(r'^[▪●•\uf075\*▸▹]', nxt):
                break
            fw = nxt.split()[0].lower().rstrip('.,;:') if nxt.split() else ''
            # Don't join a fresh named concept / section heading
            if nxt[0].isupper() and fw not in _WRAP_CONT_WORDS and len(nxt.split()) >= 4:
                break
            is_continuation = nxt[0].islower() or fw in _WRAP_CONT_WORDS or len(nxt.split()) <= 2
            if is_continuation:
                line = line.rstrip() + ' ' + nxt
                i += 1
            else:
                break

        # Strip repeated slide-title prefixes glued to the beginning
        line = _WRAP_SLIDE_STRIP.sub('', line.strip())
        if line.strip():
            joined.append(line.strip())
        i += 1
    return '\n'.join(joined)


_EC_INLINE = re.compile(r'^([A-Z][a-zA-Z0-9\s\(\)\.]{1,45}?):\s+(.{20,})$')
_EC_IS     = re.compile(
    r'^(.{2,50}?)\s+(?:is|are|concerns?|refers?\s+to|enables?|involves?)\s+(.{20,})$',
    re.I
)
_EC_GERUND   = _KP_GERUND      # reuse
_EC_BAD_FIRST = _KP_BAD_FIRST  # reuse
_EC_DANGLE = {
    'a','an','the','that','which','and','or','but','if','as','by','to','of',
    'in','on','at','for','with','from','into','than','are','is','was','were',
    'be','been','called','like','named','termed','code','following',
}


def extract_concepts_from_sentences(sentences):
    """
    Extract (concept, definition) pairs from a list of sentences.

    Detects two universal patterns:
      • "ConceptName: definition text"
      • "X is / are / concerns / enables Y"

    Returns a deduplicated list of (concept_name, definition_text) tuples.
    Works across all subjects — no domain-specific vocabulary required.
    """
    seen   = set()
    result = []

    def _valid_concept(name):
        name = name.strip().rstrip('.,;:()"')
        if not name or len(name) < 2:
            return False
        words = name.split()
        if len(words) > 5:
            return False
        if not name[0].isupper():
            return False
        if _EC_GERUND.match(name):
            return False
        first = words[0].lower() if words else ''
        return first not in _EC_BAD_FIRST

    def _valid_defn(defn):
        words = defn.strip().split()
        if len(words) < 5:
            return False
        last = words[-1].lower().rstrip('.,;:?!")')
        return last not in _EC_DANGLE

    for line in sentences:
        line = line.strip()
        if len(line) < 20:
            continue

        # Pattern 1: "ConceptName: definition"
        m = _EC_INLINE.match(line)
        if m:
            concept = m.group(1).strip().rstrip('.,;')
            colon_i = line.index(':')
            defn    = line[colon_i + 1:].strip().rstrip('.,;')
            if (_valid_concept(concept) and _valid_defn(defn)
                    and concept.lower() not in seen
                    and not re.search(r'\b(?:is|are|was|were)\b', concept, re.I)):
                seen.add(concept.lower())
                result.append((concept, defn))
                continue

        # Pattern 2: "X is/are Y"
        m = _EC_IS.match(line)
        if m:
            concept = m.group(1).strip().rstrip('.,;')
            defn    = m.group(2).strip().rstrip('.,;')
            if (_valid_concept(concept) and _valid_defn(defn)
                    and concept.lower() not in seen):
                seen.add(concept.lower())
                result.append((concept, defn))

    return result


def _format_concept_option(concept, defn):
    """
    Format a (concept, definition) pair as a self-contained MCQ option sentence.
    Returns ONLY the definition — never the 'Concept is Definition' format,
    which leaks the answer and looks like raw slide copypaste.
    """
    defn = defn.strip().rstrip('.,;:')

    # Remove circular reference (definition starts with concept name)
    defn = re.sub(rf'^(?:The\s+)?{re.escape(concept)}\s+(?:is|are|refers|means|involves|concerns)\s+',
                  '', defn, flags=re.I).strip()
    defn = re.sub(rf'^{re.escape(concept)}\s+', '', defn, flags=re.I).strip()
    if not defn:
        return ''

    defn_cap = defn[0].upper() + defn[1:] if defn else defn

    # If definition is already a sufficiently long sentence, return as-is
    words = defn.split()
    tl = ' ' + defn.lower() + ' '
    has_verb = any(v in tl for v in (
        ' is ',' are ',' was ',' were ',' involves ',' concerns ',
        ' refers ',' enables ',' allows ',' replaces ',' performs ',
        ' defined ',' stored ',' called ',' used ',' designed ',
    ))
    if len(words) >= 7 and has_verb:
        return defn_cap

    # Medium fragment (≥4 words) — capitalize and return directly
    if len(words) >= 4:
        return defn_cap

    # Very short fragment (1-3 words) — too vague on its own, skip
    return ''


# ═══════════════════════════════════════════════════════════════════════════════
#  FIX 3 — _build_mcq_from_sentences (OPTION BUILDING UPDATED)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_mcq_from_sentences(sentences, idx, subject, ollama_result=None, concepts=None):
    """
    Build an MCQ with 4 meaningful options.

    Args:
        sentences : list of sentence strings from _prepare_sentences()
        idx       : current question index (rotation key)
        subject   : subject slug, e.g. 'software_engineering', 'data_structures'. If None, defaults to 'general'.
        ollama_result: optional parsed Ollama Qwen dict
        concepts  : optional list of (concept, definition) tuples from
                    extract_concepts_from_sentences() — used for option text

    When `concepts` is provided, options are formatted as complete sentences
    using _format_concept_option(), eliminating raw fragment options like
    "possesses better quality factors" or "it in a new form".
    """

    if subject is None:
        subject = 'general'
    sentence = sentences[idx % len(sentences)]

    # ── Use Ollama result when it carries full option list ─────────────────
    if ollama_result and isinstance(ollama_result, dict):
        candidate = ollama_result.get("question", "").strip()
        q_text_ollama = candidate if (candidate and not _is_garbage_text(candidate)) else None
        opts = ollama_result.get("options")
        if isinstance(opts, list) and len(opts) >= 4 and q_text_ollama:
            return {
                "question_text": q_text_ollama,
                "question_type": "MCQ",
                "difficulty": "medium",
                "marks": 1,
                "options": {chr(65 + i): str(o) for i, o in enumerate(opts[:4])},
                "correct_answer": str(ollama_result.get("correct_option", "A")).strip().upper()[:1] or "A",
                "model_used": "Ollama-Qwen-2.5-7B",
            }

    # ── Build stem — concept-first, never fall back to subject/course title ──
    topic_raw = _extract_key_phrase(sentence)
    # Reject off-topic extracted phrases (e.g. DB concepts in SE paper)
    if topic_raw and not _is_on_topic(topic_raw, subject):
        topic_raw = None
    # If extraction failed, try using the first valid concept from the concepts list
    if not topic_raw and concepts:
        ci = idx % len(concepts)
        cand = concepts[ci][0]
        if _is_on_topic(cand, subject):
            topic_raw = cand
    topic  = topic_raw or subject.replace("_", " ")
    q_text = _build_mcq_stem(topic, idx, subject)
    # If stem is invalid (topic=subject title etc.), try cycling through concepts
    if q_text is None and concepts:
        for offset in range(1, min(len(concepts) + 1, 8)):
            alt_c, _ = concepts[(idx + offset) % len(concepts)]
            if not _is_on_topic(alt_c, subject):
                continue
            q_text = _build_mcq_stem(alt_c, idx, subject)
            if q_text:
                topic = alt_c
                break
    # Final fallback: use sentence as a definition-check question (only if on-topic)
    if q_text is None:
        clean_sent = sentence.strip().rstrip('.!?')[:100]
        if _is_on_topic(clean_sent, subject):
            q_text = f"Which statement is TRUE about the following: {clean_sent}?"
        else:
            # Off-topic sentence — use a generic SE/subject truth stem
            bank = _SUBJECT_TOPIC_BANKS.get(subject, _SUBJECT_TOPIC_BANKS['general'])
            _bank_topic = bank[idx % len(bank)]
            q_text = f"Which of the following correctly describes {_bank_topic}?"

    # ── Concept-aware option building (new path) ───────────────────────────
    if concepts:
        ci = idx % len(concepts)
        correct_concept, correct_defn = concepts[ci]
        # Only use concept if it's on-topic for the target subject
        if not _is_on_topic(correct_concept, subject) or not _is_on_topic(correct_defn, subject):
            # Try to find an on-topic concept
            _found_ontopic = False
            for _co in range(len(concepts)):
                _cc, _cd = concepts[(_co + idx) % len(concepts)]
                if _is_on_topic(_cc, subject) and _is_on_topic(_cd, subject):
                    correct_concept, correct_defn = _cc, _cd
                    _found_ontopic = True
                    break
            if not _found_ontopic:
                correct_concept, correct_defn = '', ''
        correct_opt = _format_concept_option(correct_concept, correct_defn)
        # If correct option is too short/empty or off-topic, use subject pool
        if not correct_opt or len(correct_opt.split()) < 4:
            _sent_opt = _sanitize_option_text(sentence.strip())
            if _sent_opt and _is_on_topic(_sent_opt, subject):
                correct_opt = _sent_opt
            else:
                # All source content is off-topic — use subject correct pool
                _subj_key = subject.lower() if subject else 'generic'
                for k in _QG_LAST_RESORT:
                    if k in _subj_key:
                        correct_opt = _QG_LAST_RESORT[k][idx % len(_QG_LAST_RESORT[k])]
                        break
                else:
                    correct_opt = _QG_LAST_RESORT['generic'][idx % len(_QG_LAST_RESORT['generic'])]

        # Distractors: other concept pairs (must be on-topic)
        random.seed(idx + 7)
        others = [(c, d) for j, (c, d) in enumerate(concepts)
                   if j != ci and _is_on_topic(c, subject) and _is_on_topic(d, subject)]
        random.shuffle(others)
        distractors = []
        for c2, d2 in others:
            opt = _format_concept_option(c2, d2)
            if opt and len(opt.split()) >= 4 and opt != correct_opt and opt not in distractors:
                distractors.append(opt)
            if len(distractors) >= 3:
                break

        # Pad with sanitised sentences if still short
        if len(distractors) < 3:
            other_sents = [
                _sanitize_option_text(s)
                for k, s in enumerate(sentences)
                if k != idx % len(sentences) and len(s.strip()) > 15
            ]
            random.seed(idx + 13)
            random.shuffle(other_sents)
            for d in other_sents:
                if (_is_complete_sentence(d, min_words=5)
                        and d != correct_opt and d not in distractors
                        and _is_on_topic(d, subject)):
                    distractors.append(d)
                if len(distractors) >= 3:
                    break

        # Final pad with generic distractors
        for g in _build_generic_distractors(topic, subject):
            if len(distractors) >= 3:
                break
            if g not in distractors:
                distractors.append(g)

    else:
        # ── Original sentence-based option building (fallback / code material) ─
        ollama_ans = (ollama_result or {}).get("answer", "").strip() if ollama_result else ""
        correct_opt = _sanitize_option_text(
            ollama_ans if (ollama_ans and not _is_garbage_text(ollama_ans)) else sentence.strip()
        )

        all_other = [
            _sanitize_option_text(s.strip())
            for k, s in enumerate(sentences)
            if k != idx % len(sentences) and len(s.strip()) > 15
        ]
        random.seed(idx)
        random.shuffle(all_other)

        distractors = []
        for d in all_other:
            if not _is_complete_sentence(d, min_words=5):
                continue
            if not _is_on_topic(d, subject):
                continue
            if d != correct_opt and d not in distractors:
                distractors.append(d)
            if len(distractors) >= 3:
                break

        generic = _build_generic_distractors(topic, subject)
        while len(distractors) < 3:
            distractors.append(generic[len(distractors) % len(generic)])

    # ── Randomise correct-answer position (unchanged) ─────────────────────
    options_list = [correct_opt] + distractors[:3]
    random.seed(idx + 42)
    answer_idx = random.randint(0, 3)
    options_list[0], options_list[answer_idx] = options_list[answer_idx], options_list[0]
    correct_letter = chr(65 + answer_idx)

    return {
        "question_text": q_text,
        "question_type": "MCQ",
        "difficulty": "medium",
        "marks": 1,
        "options": {
            "A": options_list[0],
            "B": options_list[1],
            "C": options_list[2],
            "D": options_list[3],
        },
        "correct_answer": correct_letter,
        "model_used": "Ollama-Qwen-2.5-7B" if ollama_result else "Rule-based",
    }


def _postprocess_generated_questions(questions, subject, num_questions):
    """
    Final quality gate: normalize type, remove garbage/repetition, enforce coherence.
    """
    cleaned = []
    seen_stems = set()
    used_topics = set()  # FIX-4: prevent duplicate MCQ concepts
    used_mcq_answer_keys = set()

    for i, q in enumerate(questions or []):
        if not isinstance(q, dict):
            continue

        q_type = _normalize_question_type(q.get("question_type"))
        q_text = _clean_text_fragment(q.get("question_text") or q.get("question") or "")
        topic  = _extract_key_phrase(q_text) or subject.replace("_", " ")
        if len(topic) < 4:
            topic = "the concept"
        # Reject off-topic topics — fall back to subject bank
        if not _is_on_topic(topic, subject):
            bank = _SUBJECT_TOPIC_BANKS.get(subject, _SUBJECT_TOPIC_BANKS['general'])
            topic = bank[i % len(bank)]

        if q_type == "MCQ":
            # v46: Preserve HF Space stems — they are already clean and well-formed.
            # Only rebuild stem for locally-generated questions where topic extraction works.
            _model = q.get("model_used", "")
            if _model in ("Template", "Ollama-Qwen-2.5-7B") and q_text and len(q_text) > 20:
                new_stem = None  # keep existing q_text from HF Space
            else:
                new_stem = _build_mcq_stem(topic, i, subject)
            if new_stem:
                q_text = new_stem
            elif q_text:
                # Keep existing q_text ONLY if it doesn't embed subject/course title as its concept
                _qt_lower = q_text.strip().lower()
                _bad_pat = re.search(
                    r'\b(what is|key purpose of|best describes|correctly explains|statement best)\b',
                    _qt_lower
                )
                _has_title = any(t in _qt_lower for t in _QG_SUBJECT_TITLES)
                if _bad_pat and _has_title:
                    continue  # Bad subject-title stem — skip this MCQ entirely
                # Else keep the existing q_text (good concept-specific stem)
            else:
                continue  # no valid concept and no existing q_text

            raw_opts = q.get("options") if isinstance(q.get("options"), dict) else {}
            orig_correct_key = str(q.get("correct_answer") or "A").strip().upper()[:1]

            # Sanitize options while preserving key→value mapping
            sanitized_map = {}  # key → sanitized value (only survivors)
            for key in sorted(raw_opts.keys()):
                val = _sanitize_option_text(raw_opts.get(key))
                if _is_complete_sentence(val, min_words=5) and _is_on_topic(val, subject):
                    sanitized_map[key] = val

            # Track correct answer VALUE (not just key) so we can find it after rebuild
            correct_val = sanitized_map.get(orig_correct_key)

            # Fill missing slots with generic distractors
            if len(sanitized_map) < 4:
                base = _sanitize_option_text(q.get("model_answer") or q.get("explanation") or "")
                if _is_complete_sentence(base, min_words=5) and base not in sanitized_map.values():
                    for label in ('A', 'B', 'C', 'D'):
                        if label not in sanitized_map:
                            sanitized_map[label] = base
                            break
                for d in _build_generic_distractors(topic, subject):
                    if len(sanitized_map) >= 4:
                        break
                    if d not in sanitized_map.values():
                        for label in ('A', 'B', 'C', 'D'):
                            if label not in sanitized_map:
                                sanitized_map[label] = d
                                break

            # Dedup by content while keeping key mapping
            uniq_map = {}
            seen_opt = set()
            for key in sorted(sanitized_map.keys()):
                k = re.sub(r'[^a-z0-9]+', ' ', sanitized_map[key].lower()).strip()
                if not k or k in seen_opt:
                    continue
                seen_opt.add(k)
                uniq_map[key] = sanitized_map[key]

            if len(uniq_map) < 4:
                continue

            # Build final option_map from first 4 keys in order
            final_keys = sorted(uniq_map.keys())[:4]
            option_map = {chr(65 + oi): uniq_map[final_keys[oi]] for oi in range(4)}

            # Find correct answer: match by VALUE first, then fall back to key
            correct = "A"
            if correct_val:
                for label, val in option_map.items():
                    if val == correct_val:
                        correct = label
                        break
            elif orig_correct_key in option_map:
                correct = orig_correct_key

            normalized = {
                "question_text": q_text,
                "question_type": "MCQ",
                "difficulty": q.get("difficulty", "medium"),
                "marks": int(q.get("marks") or 1),
                "options": option_map,
                "correct_answer": correct,
                "model_answer": None,
                "model_used": q.get("model_used", "Hybrid"),
            }
            normalized["options"], normalized["correct_answer"] = _shuffle_mcq_options(
                normalized.get("options"), normalized.get("correct_answer")
            )
        elif q_type == "Short Answer":
            if not q_text or _SUBJECTIVE_BAD_START.search(q_text):
                q_text = _repair_subjective_stem("Short Answer", topic)
            model_answer = _sentence_case(q.get("model_answer") or q.get("answer") or "")
            if not _is_complete_sentence(model_answer, min_words=5):
                model_answer = _sentence_case(
                    q.get("explanation") or
                    f"{topic} is an important concept in {subject.replace('_', ' ')}"
                )
            normalized = {
                "question_text": q_text,
                "question_type": "Short Answer",
                "difficulty": q.get("difficulty", "medium"),
                "marks": int(q.get("marks") or 3),
                "options": None,
                "correct_answer": None,
                "model_answer": model_answer[:260],
                "model_used": q.get("model_used", "Hybrid"),
            }
        else:
            if not q_text or _SUBJECTIVE_BAD_START.search(q_text):
                q_text = _repair_subjective_stem("Long Answer", topic)
            model_answer = _sentence_case(q.get("model_answer") or q.get("answer") or "")
            if not _is_complete_sentence(model_answer, min_words=7):
                model_answer = _sentence_case(
                    f"{topic} can be analyzed in terms of purpose, "
                    f"implementation steps, benefits, and limitations"
                )
            normalized = {
                "question_text": q_text,
                "question_type": "Long Answer",
                "difficulty": q.get("difficulty", "hard"),
                "marks": int(q.get("marks") or 5),
                "options": None,
                "correct_answer": None,
                "model_answer": model_answer[:520],
                "model_used": q.get("model_used", "Hybrid"),
            }

        stem_key = re.sub(r'[^a-z0-9]+', ' ', normalized["question_text"].lower()).strip()
        if not stem_key or stem_key in seen_stems:
            continue
        seen_stems.add(stem_key)
        # FIX-4: skip MCQs whose concept was already covered — avoids repetitive questions
        if normalized["question_type"] == "MCQ":
            topic_key = re.sub(r'[^a-z0-9]+', '', topic.lower())
            if topic_key and topic_key in used_topics:
                continue
            used_topics.add(topic_key)
            # Additional dedup: prevent repeated concept hidden behind different stems.
            corr = normalized.get("correct_answer") or "A"
            corr_text = ""
            if isinstance(normalized.get("options"), dict):
                corr_text = normalized["options"].get(corr, "")
            ans_key = _canonical_topic_key(corr_text)
            if ans_key and ans_key in used_mcq_answer_keys:
                continue
            if ans_key:
                used_mcq_answer_keys.add(ans_key)
        cleaned.append(normalized)
        if len(cleaned) >= num_questions:
            break

    # Coverage boost for DB: diversify stems when most MCQs hit same concept family.
    if subject == "database_fundamentals":
        mcq_idx = [i for i, q in enumerate(cleaned) if q.get("question_type") == "MCQ"]
        seen_cov = set()
        for i in mcq_idx:
            k = _canonical_topic_key(cleaned[i].get("question_text", ""))
            if k:
                seen_cov.add(k)
        if mcq_idx and len(seen_cov) < min(4, len(mcq_idx)):
            bank = _SUBJECT_TOPIC_BANKS.get("database_fundamentals", [])
            for pos, i in enumerate(mcq_idx):
                topic = bank[pos % len(bank)] if bank else "database concept"
                cleaned[i]["question_text"] = _build_mcq_stem(topic, pos, "database_fundamentals") or cleaned[i]["question_text"]

    return cleaned


def _build_short_answer(sentences, idx, subject, ollama_result=None, concepts=None):
    """Build a Short Answer question."""
    sentence = sentences[idx % len(sentences)]
    q_text = None
    model_answer = None

    if ollama_result and isinstance(ollama_result, dict):
        candidate = ollama_result.get("question", "").strip()
        if candidate and not _is_garbage_text(candidate):
            q_text = candidate
        ans = ollama_result.get("answer", "").strip()
        if ans and not _is_garbage_text(ans):
            model_answer = ans

    topic = _pick_topic(sentences, idx, subject, concepts)
    if not q_text or _SUBJECTIVE_BAD_START.search(q_text):
        _subj_label = subject.replace('_', ' ')
        _topic_eq_subj = (topic.lower().strip() == _subj_label.lower().strip())
        templates = [
            f"Define {topic} in 2-3 lines.",
            (f"Briefly explain why {topic} is important and give a practical example."
             if _topic_eq_subj
             else f"Briefly explain why {topic} is important in {_subj_label}."),
            f"Write a short note on {topic}.",
            f"State one benefit and one challenge of {topic}.",
        ]
        q_text = templates[idx % len(templates)]

    return {
        "question_text": q_text,
        "question_type": "Short Answer",
        "difficulty": "medium",
        "marks": 3,
        "options": None,
        "correct_answer": None,
        "model_answer": _sentence_case(model_answer or sentence[:250]),
        "model_used": "Ollama-Qwen-2.5-7B" if ollama_result else "Rule-based",
    }


def _build_long_answer(sentences, idx, subject, ollama_result=None, concepts=None):
    """Build a Long Answer question."""
    sentence = sentences[idx % len(sentences)]
    q_text = None
    model_answer = None

    if ollama_result and isinstance(ollama_result, dict):
        candidate = ollama_result.get("question", "").strip()
        if candidate and not _is_garbage_text(candidate):
            q_text = candidate
        ans = ollama_result.get("answer", "").strip()
        if ans and not _is_garbage_text(ans):
            model_answer = ans

    topic = _pick_topic(sentences, idx, subject, concepts)
    if not q_text or _SUBJECTIVE_BAD_START.search(q_text):
        templates = [
            f"Explain {topic} in detail and include one real-world example.",
            f"Analyze how {topic} contributes to the overall system and discuss its importance.",
            f"Discuss implementation steps, benefits, and challenges of {topic}.",
            f"Critically evaluate {topic} and suggest best practices for projects.",
        ]
        q_text = templates[idx % len(templates)]

    return {
        "question_text": q_text,
        "question_type": "Long Answer",
        "difficulty": "hard",
        "marks": 5,
        "options": None,
        "correct_answer": None,
        "model_answer": _sentence_case(model_answer or sentence[:500]),
        "model_used": "Ollama-Qwen-2.5-7B" if ollama_result else "Rule-based",
    }


def _clean_hf_space_questions(questions):
    """
    Post-process questions from HF Space to ensure clean display.
    """
    import re as _re

    _DANGLING = {
        'a', 'an', 'the', 'that', 'which', 'who', 'whom', 'whose',
        'and', 'or', 'but', 'if', 'as', 'by', 'to', 'of', 'in',
        'on', 'at', 'for', 'with', 'from', 'into', 'than', 'about',
        'when', 'where', 'while', 'although', 'because', 'since',
        'unless', 'until', 'after', 'before', 'whether', 'so',
        'those', 'these', 'them', 'they', 'its', 'their',
        'be', 'been', 'being', 'not', 'also', 'only', 'such',
    }
    # Conjunctions/transitions that signal mid-paragraph continuation (always a fragment)
    _BAD_FIRST_CONJ = {
        'but', 'and', 'or', 'yet', 'so', 'nor',
        'however', 'although', 'nevertheless', 'furthermore', 'moreover',
        'additionally', 'hence', 'thus', 'therefore', 'meanwhile',
        'otherwise', 'consequently', 'similarly', 'likewise',
    }
    # Question words — reject when used as MCQ OPTIONS (statements, not questions)
    # but NOT for question stems which legitimately start with these
    _BAD_FIRST_QWORD = {
        'why', 'how', 'what', 'when', 'where', 'which', 'who', 'whom',
    }
    def _get_short_fallback(subject):
        s = subject.replace('_', ' ')
        return [
            f"Briefly explain one key concept from {s} and give an example.",
            f"Define and describe an important term from {s}.",
            f"Explain, in 2-3 sentences, a fundamental idea from {s} with an example.",
            f"Describe, with an example, a core principle covered in {s}.",
        ]

    def _get_long_fallback(subject):
        s = subject.replace('_', ' ')
        return [
            f"Explain a key concept from {s} in detail. Include its definition, purpose, and a practical example.",
            f"Discuss an important principle from {s}. Cover definition, applications, and limitations.",
            f"Analyze a core topic from {s}. Include how it is implemented, its benefits, and any challenges.",
            f"Elaborate on a fundamental concept from {s}. Include its objectives, practical use, and supporting examples.",
        ]
    _GENERIC_FALLBACK_OPTS_BY_SUBJECT = {
        'database': [
            "Storing all records in a single flat file without any organized schema or access control",
            "Allowing every user to directly modify raw data without any validation or management layer",
            "Using no indexing strategy and performing sequential scans for every data retrieval request",
            "Duplicating all records across separate files with no mechanism to ensure data consistency",
            "Keeping all data in memory without any persistent storage mechanism or backup procedure",
            "Requiring manual recalculation of all derived values whenever the underlying data changes",
            "Eliminating all constraints to maximize data entry speed regardless of accuracy or consistency",
            "Granting unrestricted write access to all tables without any authentication or user roles",
            "Performing every query by scanning the entire dataset from beginning to end sequentially",
            "Relying on application programs to enforce all data consistency rules manually without DBMS support",
            "Defining no relationships between entities and treating all data as completely independent rows",
            "Maintaining no backup or recovery procedure and accepting permanent data loss as a risk",
            "Storing each attribute in a separate file with no linking mechanism between related records",
            "Allowing applications to bypass all security measures by directly editing data files on disk",
            "Treating every data retrieval request as a new connection with no caching or query optimization",
            "Ignoring data types entirely and storing everything as unstructured plain text without validation",
            "Processing all database queries in a fixed sequential order regardless of priority or urgency",
            "Requiring every user to write raw machine code to retrieve or update any database record",
            "Implementing each table as a completely independent entity with no foreign key relationships",
            "Hardcoding all data validation rules inside each individual application program separately",
            "A foreign key must always reference the same table in which it is originally defined",
            "Primary keys are optional for database tables and are only recommended for very large datasets",
            "Data redundancy is always beneficial in databases because it consistently improves query performance",
            "Denormalization always produces better overall results than any normalized database design approach",
            "A view in a database creates a permanent physical copy of the data in a new separate table",
            "Concurrency control mechanisms are only necessary when more than one hundred users access the data",
            "Normalization always requires splitting every table into the smallest possible atomic fragments",
            "A database schema cannot be modified or updated once the database has been populated with data",
        ],
        'python': [
            "Python requires explicit type declarations for every variable before any assignment",
            "Lists in Python are immutable sequences that cannot be modified after their initial creation",
            "The global keyword is required before every function call to access any external variable",
            "Python does not support multiple inheritance in any of its released versions",
            "Indentation in Python is purely cosmetic and does not affect program execution or structure",
            "Dictionary keys in Python can be any data type including mutable lists and sets",
            "The pass statement in Python terminates the current loop and skips all remaining iterations",
            "Python generators load all values into memory at once before yielding any results to the caller",
            "Exception handling in Python requires writing a separate handler for every possible error type",
            "Lambda functions in Python can contain multiple statements and complex control flow logic",
            "The self parameter is automatically passed by Python and never needs to appear in method definitions",
            "Tuples and lists in Python are interchangeable data types with identical performance characteristics",
            "Python modules can only be imported once during the entire lifetime of a running program",
            "Decorators in Python permanently modify the original function and cannot be removed or reversed",
            "The range function in Python generates all numbers in memory before any iteration begins",
            "Python does not support any form of functional programming techniques or patterns whatsoever",
            "String objects in Python are mutable and support direct in-place character replacement operations",
            "The init method in Python classes is called automatically when the class is deleted from memory",
            "Python virtual environments share all installed packages with the global system installation",
            "The with statement in Python is used only for exception handling and has no resource management function",
            "Python dictionaries randomly rearrange their keys on every single access or lookup operation",
            "The break statement in Python exits the entire program rather than just the enclosing loop",
            "Type hints in Python are strictly enforced at runtime and cause errors if types do not match",
            "Python closures cannot access variables from the enclosing function after it has returned",
            "All Python objects are passed by value so changes to parameters never affect the original objects",
            "The yield keyword immediately terminates a generator function and prevents any further iteration",
            "Python list slicing creates a reference to the original list rather than an independent copy",
            "The staticmethod decorator requires the class instance as its first mandatory parameter always",
        ],
        'oop': [
            "Encapsulation requires making all class attributes public to ensure full data accessibility",
            "Inheritance always creates a tight coupling between parent and child classes that cannot be avoided",
            "Polymorphism only works with classes that share the exact same parent in their hierarchy",
            "Abstract classes can be directly instantiated to create objects without implementing any methods",
            "Method overloading and method overriding are identical concepts with no practical differences",
            "Constructors can return explicit values and must be called manually by the programmer each time",
            "The open-closed principle states that classes should be open for modification and closed for extension",
            "Composition is always inferior to inheritance because it requires writing more code in every situation",
            "Design patterns are rigid rules that must be applied exactly as defined without any modifications",
            "Multiple inheritance always leads to the diamond problem and should never be used in any language",
            "Interfaces can contain fully implemented methods with complete executable logic and state",
            "High coupling between classes is desirable because it ensures components work together tightly",
            "The single responsibility principle means each class should handle all related system operations",
            "Aggregation and composition represent the exact same type of relationship between objects always",
            "Static methods can access and modify instance-specific attributes without any restrictions at all",
            "Destructors are guaranteed to execute at a precisely predictable time in every situation and language",
            "The Liskov substitution principle requires child classes to add new preconditions to parent methods",
            "Cohesion refers to the number of dependencies a class has on other external system classes",
            "Private members in a class are accessible to all other classes within the same package or module",
            "Method overriding requires the child method to have a completely different return type than the parent",
            "The factory pattern requires direct instantiation of concrete classes throughout the application code",
            "An interface can define instance variables that store state information for implementing classes",
            "The observer pattern creates a direct tight coupling between the subject and all observer objects",
            "Abstract methods in an abstract class must provide a default implementation that subclasses inherit",
            "UML class diagrams only show class names and cannot represent relationships or attributes visually",
            "The dependency inversion principle states that high-level modules should depend on low-level modules",
            "Getter and setter methods violate encapsulation principles and should be completely avoided always",
            "The prototype pattern requires creating new objects exclusively through constructors rather than cloning",
        ],
        'web': [
            "HTML is a programming language that supports variables, loops, and conditional statements natively",
            "CSS can directly modify the content of an HTML document by changing text and element structure",
            "JavaScript is executed on the server side only and never runs within the web browser environment",
            "The DOM is a static snapshot of the HTML page that cannot be modified after initial page load",
            "Responsive design requires creating a completely separate website for every possible screen size",
            "HTTP is a stateful protocol that automatically remembers all previous client-server interactions",
            "REST APIs must always return data in XML format and do not support any other serialization format",
            "Cookies and sessions are identical mechanisms with no differences in storage location or behavior",
            "AJAX requests always require a full page reload to update any content on the current web page",
            "The box model in CSS only applies to block-level elements and has no effect on inline elements",
            "JSON can contain executable functions and is designed to run logic on the client side directly",
            "Web servers can only handle one client request at a time and process all requests sequentially",
            "Bootstrap is a server-side framework that generates HTML pages dynamically on the backend only",
            "The same-origin policy prevents web browsers from loading any external resources or scripts",
            "Node.js runs JavaScript in the browser and cannot be used for any server-side applications",
            "PHP can only create static HTML pages and does not support any form of database connectivity",
            "URL routing in web applications always requires the server to have a physical file for each page",
            "Web sockets establish a new HTTP connection for every single message exchanged between endpoints",
            "The viewport meta tag is only used for print styling and has no effect on mobile device rendering",
            "Event delegation requires attaching separate event handlers to every individual child element",
            "HTTPS encryption is only necessary for banking websites and provides no benefit for other sites",
            "CSS grid and flexbox are competing standards that cannot be used together on the same web page",
            "Server-side rendering makes web applications completely unusable for search engine optimization",
            "API authentication using tokens requires sending username and password with every single request",
            "Media queries in CSS can only target the screen width and cannot detect other device characteristics",
            "Web accessibility guidelines only apply to government websites and are optional for all others",
            "Single-page applications always provide faster initial load times than traditional multi-page sites",
            "Form validation should only be done on the client side as server-side validation is fully redundant",
        ],
        'se': [
            "The waterfall model encourages going back to previous phases at any point during development",
            "Agile methodology requires completing all requirements documentation before any coding begins",
            "Unit testing should only be performed after the entire system has been fully integrated and deployed",
            "Version control systems are only useful when more than ten developers work on the same project",
            "The spiral model eliminates all project risks before the first iteration of development begins",
            "Requirements engineering is a one-time activity completed entirely during the initial project phase",
            "Software maintenance is unnecessary once the software has been thoroughly tested and deployed",
            "Prototyping always leads to poorly designed final products because prototypes become production code",
            "Code reviews are only effective when the entire team reviews every single line of code together",
            "Continuous integration requires developers to merge their code only at the end of each sprint",
            "The V-model eliminates the need for any testing activities after the coding phase is completed",
            "Risk management in software projects is only necessary for projects with very large budgets",
            "Use case diagrams completely replace all other forms of requirements documentation in modern projects",
            "Software design patterns are fixed algorithms that solve specific computational problems directly",
            "Integration testing is identical to system testing and either one provides complete test coverage",
            "The SCRUM framework does not require any meetings or ceremonies during sprint execution periods",
            "Refactoring changes the external behavior of the software to improve user-facing functionality",
            "Deployment can only occur once during the entire software development lifecycle as a final step",
            "Software metrics are only useful for management reporting and provide no value to developers",
            "Configuration management is only needed for hardware components and not for software artifacts",
            "Test-driven development requires writing all unit tests after the complete implementation is done",
            "The product backlog in Scrum is fixed at the beginning and cannot be changed during the project",
            "Software quality assurance and software testing are identical activities with no distinction at all",
            "Black-box testing requires complete knowledge of the internal source code structure and algorithms",
            "Pair programming doubles the development cost with no measurable improvement in code quality",
            "The incremental model delivers the complete system in a single release at the end of development",
            "Software reuse always introduces security vulnerabilities and should be avoided in critical systems",
            "The feasibility study is conducted only after the system has been fully designed and approved",
        ],
        'generic': [
            "All system components must be tightly coupled to ensure maximum performance and reliability",
            "Documentation is only necessary at the end of a project and provides no value during development",
            "Error handling should only be added after all features are completely implemented and tested",
            "Automated processes always produce worse results than manual approaches in every situation",
            "Security mechanisms should only be implemented for systems that store financial transaction data",
            "Performance optimization must be completed before any functional requirements are implemented",
            "Code modularity increases system complexity without providing any meaningful benefits to developers",
            "All data should be stored in a single centralized structure to minimize access time and overhead",
            "Testing is only necessary for critical system components and can be skipped for minor modules",
            "System architecture decisions are permanent and can never be changed after initial implementation",
            "Abstraction adds unnecessary layers of complexity that reduce system performance in every case",
            "All system processes should run sequentially to ensure correct ordering and prevent all conflicts",
            "Scalability planning is only necessary for systems expected to serve millions of users simultaneously",
            "User interface design has no measurable impact on system usability or user adoption rates",
            "Code comments are unnecessary because well-written source code is always completely self-explanatory",
            "All input data can be fully trusted and only needs validation when errors are reported by users",
            "System backups are only necessary for production environments and not for development or testing",
            "Algorithms with higher time complexity always produce more accurate results than faster alternatives",
            "Code reusability reduces software quality because shared components cannot be thoroughly tested",
            "Complex systems should be designed as a single monolithic unit to minimize communication overhead",
            "Standards and best practices restrict developer creativity and should be avoided in innovative work",
            "Caching is unnecessary in modern systems because hardware improvements eliminate performance issues",
            "All features should be implemented simultaneously rather than delivered in incremental releases",
            "Team collaboration tools only benefit large teams and provide no value for small development groups",
            "Error logging is unnecessary overhead that slows down performance without providing useful data",
            "System requirements never change after initial gathering and remain fixed throughout the project",
            "Load testing is only meaningful for web applications and has no relevance for desktop software",
            "Version numbering is a cosmetic practice that provides no real benefit for software release management",
        ],
    }

    def _get_fallback_opts_for_subject(subject):
        """Return the correct fallback option list for the given subject."""
        _subj_key = (subject or 'generic').lower()
        for k in _GENERIC_FALLBACK_OPTS_BY_SUBJECT:
            if k in _subj_key:
                return _GENERIC_FALLBACK_OPTS_BY_SUBJECT[k]
        return _GENERIC_FALLBACK_OPTS_BY_SUBJECT['generic']

    def _is_fragment(text):
        if not isinstance(text, str):
            return True
        t = text.strip()
        if len(t) < 10:
            return True
        if t.startswith(('"', '{', '[')) or '"options"' in t or '"question"' in t:
            return True
        if t.count('"') > 4:
            return True
        # Allow lowercase starts that contain a verb (valid definition fragments)
        if t and t[0].islower():
            _FRAG_VERBS = ('is ', 'are ', 'was ', 'were ', 'refers ', 'means ',
                           'involves ', 'allows ', 'enables ', 'provides ',
                           'stores ', 'manages ', 'defines ', 'ensures ',
                           'prevents ', 'describes ', 'represents ', 'contains ')
            if not any(v in t.lower() for v in _FRAG_VERBS):
                return True
        words = t.split()
        # Reject if first word is conjunction or transition (NOT question words —
        # those are valid for stems like "Which of the following...")
        if words and words[0].lower().rstrip('.,;:?!') in _BAD_FIRST_CONJ:
            return True
        last = words[-1].lower().rstrip('.,;:?!') if words else ''
        if last in _DANGLING:
            return True
        # Space-hyphen PDF artifacts ("end -users", "non -standard")
        if _re.search(r'\w\s+-[a-z]', t):
            return True
        if _re.search(r'\w\s*[–—]\s*\w', t) and '?' not in t and '.' not in t:
            return True
        # Physical-filing descriptions (not academic)
        _PHYS = {'drawers', 'pockets', 'filing cabinet', 'paper files',
                 'cardboard', 'folders', 'binder', 'shelf'}
        tl = t.lower()
        if sum(1 for pw in _PHYS if pw in tl) >= 2:
            return True
        # Only reject parenthetical abbreviations that are admin/scheduling (CLO, PLO)
        # Allow DB/CS acronyms like DBMS, SQL, ER, DDL, DML
        _ADMIN_ABBREVS = {'CLO', 'PLO', 'LO', 'CO', 'PO'}
        paren_match = _re.findall(r'\(([A-Z]{2,5})\)', t)
        if any(a in _ADMIN_ABBREVS for a in paren_match):
            return True
        return False

    def _fix_question_text(q):
        qt = q.get('question_text', '')
        qt_clean = _re.sub(r'(?<=[\s(])-(?=[A-Z])', '', qt).strip()
        if qt_clean != qt:
            q['question_text'] = qt_clean
            qt = qt_clean

        # Fix "adopt {negative_concept}" pattern — you don't "adopt" problems/issues
        _neg_adopt = _re.search(
            r'\badopt\s+([\w\s]+?\b(?:problems?|issues?|limitations?|drawbacks?|'
            r'disadvantages?|errors?|failures?|risks?|challenges?|conflicts?'
            r'|anomalies?|redundanc(?:y|ies))\b[\w\s]*?)[\.\?]',
            qt, _re.I)
        if _neg_adopt:
            _neg_concept = _neg_adopt.group(1).strip()
            if _neg_concept and len(_neg_concept) > 3:
                q['question_text'] = f'Which of the following best describes {_neg_concept}?'
                return q

        if not _is_fragment(qt):
            return q
        qtype = q.get('question_type', 'MCQ')
        raw = _re.sub(r'[?.!]$', '', qt).strip()
        raw = _re.sub(
            r'^(?:what\s+(?:is|are)\s+|how\s+(?:is|are)\s+|'
            r'which\s+of\s+the\s+following\s+|define\s+|explain\s+|'
            r'discuss\s+in\s+detail[:\s]+|briefly\s+explain[:\s]+|'
            r'describe\s+the\s+concept\s+(?:of\s+)?[:\s]*|'
            r'write\s+a\s+comprehensive\s+explanation\s+of\s+(?:the\s+following\s+concept[:\s]+)?|'
            r'elaborate\s+on\s+(?:the\s+following\s+)?(?:and\s+explain\s+its\s+significance\s+[^:]+[:\s]+)?|'
            r'critically\s+analyze[:\s]+)',
            '', raw, flags=_re.I).strip()
        raw = _re.sub(
            r'^(?:with\s+(?:each\s+of\s+)?|for\s+(?:each\s+)?|by\s+|'
            r'in\s+(?:the\s+context\s+of\s+|order\s+to\s+)?|'
            r'through\s+|upon\s+|at\s+(?:each\s+)?)',
            '', raw, flags=_re.I).strip()
        subj = _re.split(r'\s*[-–—]\s*|\s+(?:that|which|who|because|those|these|,)\b', raw)[0].strip()
        if ',' in subj:
            subj = subj.split(',')[0].strip()
        subj = _re.sub(r'^[\-–—\.\*\•\s]+', '', subj).strip()
        subj = subj[:70] if len(subj) > 70 else subj

        if qtype == 'Short Answer':
            q['question_text'] = (f"Briefly define and explain: {subj}."
                                  if subj and len(subj) > 6
                                  else _SHORT_FALLBACK[hash(qt) % len(_SHORT_FALLBACK)])
        elif qtype == 'Long Answer':
            q['question_text'] = (
                f"Discuss in detail the concept of {subj}. Provide relevant examples and applications."
                if subj and len(subj) > 6
                else _LONG_FALLBACK[hash(qt) % len(_LONG_FALLBACK)])
        else:
            # MCQ: wrap extracted subj in a clean template — but only if subj itself
            # is NOT an MCQ-style question pattern (which would create double-wrapping).
            _subj_is_already_mcq = (
                len(subj.split()) > 6
                or _re.search(r'\b(which\s+of|which\s+option|correctly\s+defines|'
                              r'best\s+describes|best\s+explains|accurately\s+describes|'
                              r'best\s+characterise[sd]?|most\s+accurate|'
                              r'key\s+characteristic|key\s+purpose|'
                              r'is\s+incorrect|does\s+not\s+correct)\b', subj, _re.I)
            )
            if _subj_is_already_mcq or not subj or len(subj) <= 5:
                q['question_text'] = "Which of the following statements is correct?"
            else:
                q['question_text'] = f"Which of the following best describes {subj}?"
        return q

    cleaned = []
    _subject_opts = _get_fallback_opts_for_subject(subject)
    _fallback_set = set(_subject_opts)
    import random as _rng
    for qi, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        q = _fix_question_text(q)
        if q.get('question_type') == 'MCQ' and isinstance(q.get('options'), dict):
            opts = q['options']
            keys = list(opts.keys())
            correct_key = q.get('correct_answer', 'A')
            new_opts = {}
            # Shuffle a fresh copy so each question gets different fallback distractors
            _rng.seed(qi * 137 + 97)
            fallback_pool = list(_subject_opts)
            _rng.shuffle(fallback_pool)
            fallback_idx  = 0
            for k in keys:
                v = opts.get(k, '')
                # Check fragment OR option starts with question word (options must be statements)
                _v_first = v.strip().split()[0].lower().rstrip('.,;:?!') if v.strip() else ''
                if _is_fragment(v) or _v_first in _BAD_FIRST_QWORD:
                    replacement = fallback_pool[fallback_idx % len(fallback_pool)]
                    fallback_idx += 1
                    new_opts[k] = replacement
                else:
                    v_str = _sanitize_option_text(str(v))
                    # After sanitizing, re-check if it became a fragment/empty
                    if not v_str or len(v_str) < 4:
                        replacement = fallback_pool[fallback_idx % len(fallback_pool)]
                        fallback_idx += 1
                        v_str = replacement
                    new_opts[k] = v_str
            generic_count = sum(1 for v in new_opts.values() if v in _fallback_set)
            if generic_count >= 3:
                continue
            if new_opts.get(correct_key) in _fallback_set:
                for k in keys:
                    if new_opts[k] not in _fallback_set:
                        q['correct_answer'] = k
                        break
            q['options'] = new_opts
        cleaned.append(q)
    return cleaned


def _generate_via_hf_space(text, subject, num_questions):
    """Call the remote Hugging Face Space for question generation."""
    if not HF_SPACE_URL:
        return None
    try:
        from gradio_client import Client
        import concurrent.futures
        print(f"   Calling HF Space: {HF_SPACE_URL}")
        client = Client(HF_SPACE_URL, verbose=False)
        hf_timeout = int(os.getenv("HF_SPACE_TIMEOUT", "15"))
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                client.predict,
                text=text[:8000],
                subject=subject,
                num_questions=num_questions,
                api_name="/predict",
            )
            try:
                result = future.result(timeout=hf_timeout)
            except concurrent.futures.TimeoutError:
                print(f"   HF Space timed out after {hf_timeout}s — using local Ollama")
                return None
        data = result
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, list) and data:
            data = _clean_hf_space_questions(data)
            if data:
                print(f"   HF Space returned {len(data)} clean questions")
                return data
        print("   HF Space returned empty/bad result — using local Ollama")
        return None
    except Exception as e:
        print(f"   HF Space unavailable ({type(e).__name__}) — using local Ollama")
        return None

def generate_questions_from_text(text, subject='general', num_questions=10):
    """
    Generate questions from the given text.

    Produces a mix of MCQ (4 options), Short Answer, and Long Answer questions.
    Compatible with all subjects: software_engineering, data_structures, database_systems, operating_systems, object_oriented_programming, python_programming, web_development, algorithms, machine_learning, general.
    
    PRIORITY: Try AI models FIRST (HF Space, Qwen LoRA, Ollama) for varied questions.
    FALLBACK: Use rule-based curated packs only if AI models unavailable/fail.
    """
    try:
        # ── PRIORITY 1: Remote HF Space ───────────────────────────────────────────
        if HF_SPACE_URL:
            remote_qs = _generate_via_hf_space(text, subject, num_questions)
            if remote_qs:
                remote_qs = _postprocess_generated_questions(remote_qs, subject, num_questions)
                if remote_qs:
                    return remote_qs[:num_questions]

        # ── PRIORITY 2: Qwen LoRA (GPU only) ───────────────────────────────────────
        if USE_QWEN_LORA:
            qwen_questions = _generate_with_qwen_lora(text, subject, num_questions)
            if qwen_questions:
                qwen_questions = _postprocess_generated_questions(qwen_questions, subject, num_questions)
                if qwen_questions:
                    return qwen_questions[:num_questions]

        # ── PRIORITY 3: Ollama Qwen 2.5 7B + concept-aware builders ─────────────────────
        #
        # Pre-process: join PDF continuation lines so _prepare_sentences()
        # gets whole sentences instead of broken fragments like
        # "Reengineering concepts  A good comprehension of the software…"
        processed_text = _join_wrapped_lines(text)

        sentences = _prepare_sentences(processed_text)
        if not sentences:
            return _fallback_question_generation(text, subject, num_questions)

        # Extract concept+definition pairs for cleaner MCQ options
        concepts = extract_concepts_from_sentences(sentences)

        # ── CodeBERT enrichment for code-heavy text ───────────────────────
        # When the source material contains code snippets, use CodeBERT to
        # analyse them and inject function/class/variable names as additional
        # (concept, definition) pairs.  This ensures the code-understanding
        # model is applied to its intended task.
        if detect_code_content(text):
            code_extras = extract_code_functions_and_concepts(text)
            codebert_result = analyze_code_with_codebert(text[:2048])
            _cb_tag = "(CodeBERT)" if codebert_result else "(regex-only)"
            _added = 0
            _existing_lower = {c[0].lower() for c in concepts}
            for kind, names in code_extras.items():
                for name in names:
                    # Only use substantial names (≥3 chars, not a Python keyword/import noise)
                    if (name and len(name) >= 3
                            and name.lower() not in _existing_lower
                            and name.lower() not in ('the', 'import', 'from', 'self',
                                                      'true', 'false', 'none', 'return',
                                                      'class', 'def', 'for', 'while', 'if')):
                        defn = f"{kind.rstrip('s').capitalize()} used in the codebase for {name}"
                        concepts.append((name, defn))
                        _existing_lower.add(name.lower())
                        _added += 1
            if _added:
                print(f"   🔬 Code detected — enriched {_added} concept(s) {_cb_tag}")

        print(f"   📊 {len(sentences)} sentences, {len(concepts)} concept pairs extracted")

        # Distribution: ~60% MCQ, ~25% Short, ~15% Long
        num_mcq   = max(1, round(num_questions * 0.6))
        num_short = max(1, round(num_questions * 0.25))
        num_long  = num_questions - num_mcq - num_short
        if num_long < 0:
            num_long  = 0
            num_short = num_questions - num_mcq

        print(f"   📊 Target distribution: MCQ={num_mcq}, Short={num_short}, Long={num_long}")

        questions   = []
        sent_idx    = 0
        _device     = "cuda" if (torch and torch.cuda.is_available()) else "cpu"
        # Allow Ollama calls on CPU — default 8 per generation run.
        # Set OLLAMA_MAX_CALLS_CPU=0 in .env to disable if too slow.
        max_ollama_cpu = int(os.getenv("OLLAMA_MAX_CALLS_CPU", "8"))
        max_ollama_gpu = int(os.getenv("OLLAMA_MAX_CALLS_GPU", "12"))
        max_ollama     = max_ollama_gpu if _device != "cpu" else max_ollama_cpu
        ollama_called = 0

        # Spread chunks evenly across the full document so each question
        # draws from a different section of the uploaded material.
        total_sents = len(sentences)
        step = max(1, total_sents // max(num_questions, 1))

        def _get_chunk(idx):
            """Return a 3-sentence window starting at idx, spread across doc."""
            start = (idx * step) % total_sents
            window = sentences[start:start + 3]
            return ' '.join(window)

        for i in range(num_mcq):
            ollama_result = None
            if OLLAMA_AVAILABLE and ollama_called < max_ollama:
                chunk = _get_chunk(sent_idx)
                ollama_result = generate_with_ollama(chunk, "mcq", subject)
                ollama_called += 1
            q = _build_mcq_from_sentences(
                sentences, (sent_idx * step) % total_sents, subject, ollama_result, concepts or None)
            q["question_id"] = f"q_{subject}_{i}_mcq"
            questions.append(q)
            sent_idx += 1

        for i in range(num_short):
            ollama_result = None
            if OLLAMA_AVAILABLE and ollama_called < max_ollama:
                chunk = _get_chunk(sent_idx)
                ollama_result = generate_with_ollama(chunk, "short", subject)
                ollama_called += 1
            q = _build_short_answer(sentences, (sent_idx * step) % total_sents, subject, ollama_result, concepts)
            q["question_id"] = f"q_{subject}_{i}_short"
            questions.append(q)
            sent_idx += 1

        for i in range(num_long):
            ollama_result = None
            if OLLAMA_AVAILABLE and ollama_called < max_ollama:
                chunk = _get_chunk(sent_idx)
                ollama_result = generate_with_ollama(chunk, "long", subject)
                ollama_called += 1
            q = _build_long_answer(sentences, (sent_idx * step) % total_sents, subject, ollama_result, concepts)
            q["question_id"] = f"q_{subject}_{i}_long"
            questions.append(q)
            sent_idx += 1

        questions = _postprocess_generated_questions(questions, subject, num_questions)
        if len(questions) < num_questions:
            # Only use text-based rule fallback — never use pre-built question banks
            # (question banks contain generic questions unrelated to uploaded material)
            backfill  = _fallback_question_generation(text, subject, num_questions - len(questions))
            questions = _postprocess_generated_questions(
                questions + backfill, subject, num_questions)

        print(f"   ✅ Generated {len(questions)} questions "
              f"(MCQ={num_mcq}, Short={num_short}, Long={num_long}, "
              f"Ollama calls={ollama_called}, concepts={len(concepts)})")
        return questions[:num_questions]

    except Exception as e:
        print(f"Error in question generation: {e}")
        import traceback; traceback.print_exc()
        # Only use text-based fallback — never return pre-built bank questions
        if text and len(text.strip()) > 100:
            return _fallback_question_generation(text, subject, num_questions)
        return []


def _fallback_question_generation(text, subject, num_questions):
    """Fallback to rule-based question generation if models are unavailable."""
    processed = _join_wrapped_lines(text or '')
    sentences = _prepare_sentences(processed)

    if not sentences:
        sentences = ['Explain the key concept from the provided material']

    concepts  = extract_concepts_from_sentences(sentences)
    questions = []
    num_mcq   = max(1, round(num_questions * 0.6))
    num_short = max(1, round(num_questions * 0.25))
    num_long  = num_questions - num_mcq - num_short
    if num_long < 0:
        num_long = 0

    idx = 0
    for i in range(num_mcq):
        q = _build_mcq_from_sentences(sentences, idx, subject, concepts=concepts or None)
        q["question_id"] = f"q_{subject}_{i}_mcq"
        questions.append(q)
        idx += 1

    for i in range(num_short):
        q = _build_short_answer(sentences, idx, subject, concepts=concepts)
        q["question_id"] = f"q_{subject}_{i}_short"
        questions.append(q)
        idx += 1

    for i in range(num_long):
        q = _build_long_answer(sentences, idx, subject, concepts=concepts)
        q["question_id"] = f"q_{subject}_{i}_long"
        questions.append(q)
        idx += 1

    return _postprocess_generated_questions(questions[:num_questions], subject, num_questions)


def apply_quality_improvements(questions: list, original_text: str = "", subject: str = "general") -> tuple:
    """
    Apply grounding, duplicate detection, and validation to generated questions.
    
    Returns: (improved_questions, quality_report)
    
    quality_report contains:
    {
        'grounding': {...},
        'duplicates': {...},
        'validation': {...}
    }
    """
    if not questions:
        return questions, {'grounding': None, 'duplicates': None, 'validation': None}
    
    report = {}
    
    # ── GROUNDING: Link each question to source content ────────────────────
    if ContentGroundingEngine and original_text:
        try:
            grounding_engine = ContentGroundingEngine(chunk_size=300, overlap=50)
            chunks = grounding_engine.segment_content(original_text)
            
            for q in questions:
                q = ground_question(q, grounding_engine)
            
            report['grounding'] = {
                'total_chunks': len(chunks),
                'grounded_questions': sum(1 for q in questions if q.get('is_grounded')),
                'total_questions': len(questions),
                'coverage_stats': grounding_engine.get_coverage_stats()
            }
            print(f"   🔗 Grounded {report['grounding']['grounded_questions']}/{len(questions)} questions")
        except Exception as e:
            print(f"   ⚠️  Grounding failed: {e}")
            report['grounding'] = None
    else:
        report['grounding'] = None
    
    # ── DUPLICATE DETECTION: Find and flag duplicates ─────────────────────
    if assess_question_duplicates:
        try:
            questions = assess_question_duplicates(questions)
            high_risk = sum(1 for q in questions if q.get('duplicate_risk') == 'high')
            report['duplicates'] = {
                'total_questions': len(questions),
                'high_risk_count': high_risk,
                'medium_risk_count': sum(1 for q in questions if q.get('duplicate_risk') == 'medium'),
            }
            if high_risk > 0:
                print(f"   ⚠️  Found {high_risk} high-risk duplicate(s)")
        except Exception as e:
            print(f"   ⚠️  Duplicate detection failed: {e}")
            report['duplicates'] = None
    else:
        report['duplicates'] = None
    
    # ── VALIDATION: Check for broken/incomplete questions ─────────────────
    if validate_exam_before_publishing:
        try:
            exam_data = {
                'exam_title': 'Generated Exam',
                'subject': subject,
                'total_marks': sum(q.get('marks', 1) for q in questions),
                'duration_minutes': 120,
            }
            is_valid, validation_report = validate_exam_before_publishing(exam_data, questions)
            report['validation'] = validation_report
            
            if is_valid:
                print(f"   ✅ Validation passed ({len(validation_report.get('warnings', []))} warnings)")
            else:
                print(f"   ❌ Validation failed ({len(validation_report.get('errors', []))} errors)")
        except Exception as e:
            print(f"   ⚠️  Validation failed: {e}")
            report['validation'] = None
    else:
        report['validation'] = None
    
    return questions, report

