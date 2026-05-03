import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL = 'https://uhrqrrksblibtsomntqh.supabase.co'
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVocnFycmtzYmxpYnRzb21udHFoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkyNTM0MjMsImV4cCI6MjA4NDgyOTQyM30.smiXa4SZLtPLvDDuog0fzb-bD9FuUQnOJRxOHg0J5gw'

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
