(function () {
    const EMBED_PARAM = 'embed';
    const SHELL_PAGE = 'teacher-shell.html';
    const MANAGED_FILES = new Set([
        'dashboard-teacher.html',
        'create-exam.html',
        'question-editor.html',
        'exam-preview.html',
        'exam-results.html',
        'profile.html',
        'analytics.html',
        'question-bank.html',
        'view-exam.html'
    ]);
    const DASHBOARD_VIEWS = new Set(['dashboard', 'submissions', 'results', 'students']);
    const HASH_VIEW_MAP = new Map([
        ['#recentexamssection', 'dashboard'],
        ['#examssection', 'dashboard'],
        ['#profilesection', 'dashboard'],
        ['#pendingsection', 'submissions'],
        ['#pendinggradingsection', 'submissions'],
        ['#resultssection', 'results'],
        ['#studentssection', 'students']
    ]);

    function getCurrentFile() {
        const parts = String(window.location.pathname || '').split('/');
        return (parts.pop() || '').toLowerCase();
    }

    function isManagedTeacherPage() {
        return MANAGED_FILES.has(getCurrentFile());
    }

    function isTeacherRole() {
        const role = (sessionStorage.getItem('userRole') || localStorage.getItem('userRole') || '').toLowerCase();
        return role === 'teacher';
    }

    function isEmbeddedMode() {
        const params = new URLSearchParams(window.location.search || '');
        return params.get(EMBED_PARAM) === '1' || window.self !== window.top;
    }

    function normalizeDashboardTarget(url) {
        const hash = String(url.hash || '').trim().toLowerCase();
        const requestedView = String(url.searchParams.get('view') || '').trim().toLowerCase();
        const nextView = HASH_VIEW_MAP.get(hash) || (DASHBOARD_VIEWS.has(requestedView) ? requestedView : 'dashboard');
        return nextView === 'dashboard'
            ? 'dashboard-teacher.html?view=dashboard'
            : `dashboard-teacher.html?view=${encodeURIComponent(nextView)}`;
    }

    function normalizeTeacherTarget(rawTarget) {
        const fallback = 'dashboard-teacher.html?view=dashboard';
        if (!rawTarget) return fallback;

        try {
            const url = new URL(rawTarget, window.location.href);
            if (url.origin !== window.location.origin) return null;

            const file = (url.pathname.split('/').pop() || '').toLowerCase();
            if (!MANAGED_FILES.has(file)) return null;

            if (file === 'dashboard-teacher.html') {
                return normalizeDashboardTarget(url);
            }

            const normalized = new URL(file, window.location.href);
            normalized.search = url.search;
            normalized.hash = url.hash;
            return `${normalized.pathname.split('/').pop()}${normalized.search}${normalized.hash}`;
        } catch (_) {
            return null;
        }
    }

    function buildShellUrl(target) {
        const normalizedTarget = normalizeTeacherTarget(target) || 'dashboard-teacher.html?view=dashboard';
        return `${SHELL_PAGE}?page=${encodeURIComponent(normalizedTarget)}`;
    }

    function navigateTeacherShell(target, options = {}) {
        const normalizedTarget = normalizeTeacherTarget(target);
        if (!normalizedTarget) {
            if (typeof target === 'string' && target) {
                if (options.replace) window.location.replace(target);
                else window.location.href = target;
            }
            return null;
        }

        if (isEmbeddedMode()) {
            try {
                if (window.parent && window.parent !== window && window.parent.TeacherShellHost && typeof window.parent.TeacherShellHost.navigate === 'function') {
                    window.parent.TeacherShellHost.navigate(normalizedTarget, options);
                    return normalizedTarget;
                }
            } catch (_) {
                // Fall back to iframe-local navigation below.
            }
            if (options.replace) window.location.replace(normalizedTarget);
            else window.location.href = normalizedTarget;
            return normalizedTarget;
        }

        if (isTeacherRole()) {
            const shellUrl = buildShellUrl(normalizedTarget);
            if (options.replace) window.location.replace(shellUrl);
            else window.location.href = shellUrl;
            return normalizedTarget;
        }

        if (options.replace) window.location.replace(normalizedTarget);
        else window.location.href = normalizedTarget;
        return normalizedTarget;
    }

    function interceptTeacherLinks() {
        document.addEventListener('click', function (event) {
            const anchor = event.target && event.target.closest ? event.target.closest('a[href]') : null;
            if (!anchor) return;
            if (anchor.hasAttribute('download')) return;
            if ((anchor.getAttribute('target') || '').toLowerCase() === '_blank') return;

            const href = (anchor.getAttribute('href') || '').trim();
            if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('mailto:') || href.startsWith('tel:')) return;

            const normalizedTarget = normalizeTeacherTarget(href);
            if (!normalizedTarget) return;

            event.preventDefault();
            navigateTeacherShell(normalizedTarget);
        });
    }

    function buildCurrentPageRef() {
        const file = getCurrentFile();
        const url = new URL(window.location.href);
        url.searchParams.delete(EMBED_PARAM);
        const search = url.searchParams.toString();
        return `${file}${search ? `?${search}` : ''}${url.hash || ''}`;
    }

    function markEmbeddedBody() {
        const apply = function () {
            if (!document.body) return;
            document.body.classList.add('embedded-shell');
        };

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', apply, { once: true });
        } else {
            apply();
        }
    }

    if (!isManagedTeacherPage()) {
        return;
    }

    window.TeacherShellNav = {
        buildShellUrl,
        navigate: navigateTeacherShell,
        normalizeTarget: normalizeTeacherTarget,
        isEmbeddedMode
    };

    interceptTeacherLinks();

    if (isEmbeddedMode()) {
        window.__TEACHER_SHELL_EMBEDDED__ = true;
        markEmbeddedBody();
        return;
    }

    if (isTeacherRole()) {
        window.location.replace(buildShellUrl(buildCurrentPageRef()));
    }
})();
