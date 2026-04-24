(function () {
    const SUPABASE_URL = 'https://uhrqrrksblibtsomntqh.supabase.co';
    const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVocnFycmtzYmxpYnRzb21udHFoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkyNTM0MjMsImV4cCI6MjA4NDgyOTQyM30.smiXa4SZLtPLvDDuog0fzb-bD9FuUQnOJRxOHg0J5gw';

    function getBackendBase() {
        const rawHost = window.location.hostname || '';
        // Local development
        if (rawHost === 'localhost' || rawHost === '127.0.0.1' || !rawHost) {
            return 'http://127.0.0.1:5000/api';
        }
        // Production — use Render backend
        return 'https://smart-web-exam-system.onrender.com/api';
    }

    function readAccessTokenFromStorage() {
        try {
            const storagePrefix = `sb-${new URL(SUPABASE_URL).hostname.split('.')[0]}-auth-token`;
            const raw = localStorage.getItem(storagePrefix) || sessionStorage.getItem(storagePrefix);
            if (!raw) return '';

            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) {
                const session = parsed[0] || {};
                return session.access_token || '';
            }
            return parsed && parsed.access_token ? parsed.access_token : '';
        } catch (_) {
            return '';
        }
    }

    async function getAccessToken(supabaseClient) {
        if (!supabaseClient || !supabaseClient.auth || typeof supabaseClient.auth.getSession !== 'function') {
            return readAccessTokenFromStorage();
        }
        try {
            const { data, error } = await supabaseClient.auth.getSession();
            if (error) return readAccessTokenFromStorage();
            if (!data || !data.session) return readAccessTokenFromStorage();

            const session = data.session;
            // Proactively refresh if token expires within 5 minutes
            const expiresAt = session.expires_at; // Unix timestamp in seconds
            if (expiresAt && (expiresAt - Math.floor(Date.now() / 1000)) < 300) {
                try {
                    const { data: refreshed } = await supabaseClient.auth.refreshSession();
                    if (refreshed?.session?.access_token) {
                        return refreshed.session.access_token;
                    }
                } catch (_) { /* fall through to existing token */ }
            }
            return session.access_token || readAccessTokenFromStorage();
        } catch (_) {
            return readAccessTokenFromStorage();
        }
    }

    async function buildAuthHeaders(supabaseClient, headers) {
        const merged = { ...(headers || {}) };
        
        // Add Supabase auth token
        const token = await getAccessToken(supabaseClient);
        if (token) {
            merged.Authorization = `Bearer ${token}`;
        }
        
        // Add RBAC headers for backend permission checking
        const userEmail = localStorage.getItem('userEmail');
        const userId = localStorage.getItem('userId');
        const userRole = localStorage.getItem('userRole');
        
        if (userEmail) merged['X-User-Email'] = userEmail;
        if (userId) merged['X-User-ID'] = userId;
        if (userRole) merged['X-User-Role'] = userRole;
        
        return merged;
    }

    window.AppConfig = {
        SUPABASE_URL,
        SUPABASE_ANON_KEY,
        getBackendBase,
        getAccessToken,
        buildAuthHeaders,
    };

    // ── Global error boundary — show toast instead of blank screen ──
    window.addEventListener('unhandledrejection', (event) => {
        const msg = String(event?.reason?.message || event?.reason || 'An unexpected error occurred');
        // Don't show for network/auth errors that are handled elsewhere
        if (msg.includes('401') || msg.includes('403') || msg.includes('AbortError')) return;
        console.error('[Global Error]', event.reason);
        // Show a non-intrusive toast if the function exists
        if (typeof window.showToast === 'function') {
            window.showToast('Something went wrong: ' + msg.slice(0, 80), 'error', 5000);
        }
    });

    window.addEventListener('error', (event) => {
        // Only catch script errors, not resource load failures
        if (!event.message) return;
        console.error('[Global Script Error]', event.message, event.filename, event.lineno);
    });
})();
