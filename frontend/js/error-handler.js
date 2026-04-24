// Global error boundary for Smart Exam System
(function() {
    window.addEventListener('unhandledrejection', function(event) {
        const msg = String(event.reason?.message || event.reason || 'Unknown error');
        // Don't show toast for network errors during exam (handled separately)
        if (msg.includes('Failed to fetch') || msg.includes('NetworkError')) return;
        if (typeof window.showToast === 'function') {
            window.showToast('Something went wrong: ' + msg.slice(0, 80), 'error');
        }
        console.error('[Global Error]', event.reason);
    });

    window.addEventListener('error', function(event) {
        if (event.filename && event.filename.includes('supabase')) return;
        console.error('[Script Error]', event.message, event.filename, event.lineno);
    });
})();
