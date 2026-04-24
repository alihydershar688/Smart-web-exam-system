-- ===========================================
-- RBAC EXTENSION - MINIMAL
-- ===========================================
-- Just add course enrollments for RBAC
-- Run this SQL in Supabase SQL Editor

-- Course enrollments linking users to exams/courses
CREATE TABLE IF NOT EXISTS course_enrollments (
  enrollment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  course_code VARCHAR(100) NOT NULL,
  enrollment_role VARCHAR(50) NOT NULL CHECK (enrollment_role IN ('student', 'teacher', 'ta')),
  enrollment_status VARCHAR(50) DEFAULT 'active',
  enrolled_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_enrollments_user ON course_enrollments(user_id);
CREATE INDEX IF NOT EXISTS idx_enroll_course_code ON course_enrollments(course_code);

-- ✅ Done! Backend RBAC is now ready to use.
