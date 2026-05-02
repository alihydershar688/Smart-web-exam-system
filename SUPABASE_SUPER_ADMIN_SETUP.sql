-- ============================================================
-- SUPER ADMIN SETUP — Smart Exam System
-- Run this in Supabase SQL Editor
-- ============================================================

-- 1. Update Ali Hyder's role to super_admin
UPDATE public.users
SET role = 'super_admin', status = 'active'
WHERE email = 'alihydershar688@gmail.com';

-- 2. Create audit_log table
CREATE TABLE IF NOT EXISTS public.audit_log (
    id          uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    actor_email text NOT NULL,
    action      text NOT NULL,
    target      text,
    extra       text,
    created_at  timestamptz DEFAULT now()
);

-- 3. Create system_settings table
CREATE TABLE IF NOT EXISTS public.system_settings (
    key         text PRIMARY KEY,
    value       text,
    message     text,
    updated_by  text,
    updated_at  timestamptz DEFAULT now()
);

-- 4. Insert default maintenance mode setting
INSERT INTO public.system_settings (key, value, message, updated_by)
VALUES ('maintenance_mode', 'false', '', 'system')
ON CONFLICT (key) DO NOTHING;

-- 5. Verify
SELECT email, role, status FROM public.users WHERE email = 'alihydershar688@gmail.com';
