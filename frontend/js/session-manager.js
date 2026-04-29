(function () {
    const ACTIVE_AUTH_KEYS = [
        'isLoggedIn',
        'userRole',
        'userEmail',
        'userId',
        'userName',
        'userFirstName',
        'userLastName',
        'userDepartment',
        'userPhone',
        'userAddress',
        'userBio',
        'userBatch',
        'studentId',
        'teacherId',
        'adminId',
        'deviceId'
    ];
    const LOGIN_AT_KEY = 'authLoginAt';
    const LAST_ACTIVITY_KEY = 'authLastActivityAt';
    const LOGOUT_BROADCAST_KEY = 'authLogoutAt';
    const PAGE_TRANSITION_KEY = 'authPageTransitionAt';
    const DEFAULT_IDLE_TIMEOUT_MS = 60 * 60 * 1000;      // 60 minutes idle timeout
    const DEFAULT_ABSOLUTE_TIMEOUT_MS = 12 * 60 * 60 * 1000; // 12 hours absolute
    /* ── Session timeout disabled for demo stability ── */
    const TESTING_MODE_DISABLE_TIMEOUT = true;
    const ACTIVITY_THROTTLE_MS = 15000;
    const CHECK_INTERVAL_MS = 30000;
    const LOCK_RENEW_INTERVAL_MS = 60 * 1000;
    const PAGE_TRANSITION_GRACE_MS = 10000;
    const DEVICE_ID_KEY = 'deviceId';

    let currentConfig = null;
    let checkTimer = null;
    let renewTimer = null;
    let lastTouchAt = 0;
    let storageHandlerBound = false;
    let authClient = null;
    
    /* ── Session timeout disabled — keep user logged in ── */
    const DISABLE_SESSION_TIMEOUT = true;

    function nowMs() {
        return Date.now();
    }

    function getStore(key) {
        return sessionStorage.getItem(key);
    }

    function setStore(key, value) {
        sessionStorage.setItem(key, value);
        localStorage.setItem(key, value);
    }

    function removeStore(key) {
        sessionStorage.removeItem(key);
        localStorage.removeItem(key);
    }

    function readNumber(key) {
        const raw = getStore(key) || localStorage.getItem(key);
        const value = Number(raw);
        return Number.isFinite(value) ? value : 0;
    }

    function buildLoginUrl(baseUrl) {
        const loginUrl = baseUrl || 'login.html';
        const currentPage = window.location.pathname.split('/').pop() || 'index.html';
        return `${loginUrl}?return=${encodeURIComponent(currentPage)}`;
    }

    function clearAuthStorage() {
        [...ACTIVE_AUTH_KEYS, LOGIN_AT_KEY, LAST_ACTIVITY_KEY, PAGE_TRANSITION_KEY].forEach((key) => {
            if (key === DEVICE_ID_KEY) return;
            removeStore(key);
        });
    }

    function getNavigationType() {
        try {
            const entries = performance.getEntriesByType && performance.getEntriesByType('navigation');
            if (entries && entries.length > 0 && entries[0] && entries[0].type) {
                return entries[0].type;
            }
            if (performance && performance.navigation) {
                if (performance.navigation.type === 1) return 'reload';
                if (performance.navigation.type === 0) return 'navigate';
            }
        } catch (_) {
        }
        return 'navigate';
    }

    function hasSameOriginReferrer() {
        try {
            if (!document.referrer) return false;
            const referrerUrl = new URL(document.referrer, window.location.href);
            return referrerUrl.origin === window.location.origin;
        } catch (_) {
            return false;
        }
    }

    function hasRecentPageTransition() {
        const raw = Number(localStorage.getItem(PAGE_TRANSITION_KEY) || 0);
        return Number.isFinite(raw) && raw > 0 && (nowMs() - raw) <= PAGE_TRANSITION_GRACE_MS;
    }

    function restoreSessionFromLocalStorage() {
        if (sessionStorage.getItem('isLoggedIn')) return true;
        if (localStorage.getItem('isLoggedIn') !== 'true') return false;
        const navigationType = getNavigationType();
        const canRestore =
            navigationType === 'reload'
            || hasSameOriginReferrer()
            || hasRecentPageTransition();

        if (!canRestore) return false;

        [...ACTIVE_AUTH_KEYS, LOGIN_AT_KEY, LAST_ACTIVITY_KEY].forEach((key) => {
            const value = localStorage.getItem(key);
            if (value !== null && value !== undefined && value !== '') {
                sessionStorage.setItem(key, value);
            }
        });
        localStorage.removeItem(PAGE_TRANSITION_KEY);
        return !!sessionStorage.getItem('isLoggedIn');
    }

    function markPageTransition() {
        if (!getStore('isLoggedIn')) return;
        localStorage.setItem(PAGE_TRANSITION_KEY, String(nowMs()));
    }

    function getBackendBase() {
        if (window.AppConfig && typeof window.AppConfig.getBackendBase === 'function') {
            return window.AppConfig.getBackendBase();
        }
        const rawHost = window.location.hostname || '';
        const backendHost = (rawHost === 'localhost' || !rawHost) ? '127.0.0.1' : rawHost;
        const proto = (window.location.protocol === 'file:') ? 'http:' : window.location.protocol;
        return `${proto}//${backendHost}:5000/api`;
    }

    function getAuthClient() {
        if (authClient) return authClient;
        if (!window.AppConfig || !window.supabase || typeof window.supabase.createClient !== 'function') {
            return null;
        }
        authClient = window.supabase.createClient(
            window.AppConfig.SUPABASE_URL,
            window.AppConfig.SUPABASE_ANON_KEY
        );
        return authClient;
    }

    async function buildAuthHeaders(headers) {
        if (window.AppConfig && typeof window.AppConfig.buildAuthHeaders === 'function') {
            return window.AppConfig.buildAuthHeaders(getAuthClient(), headers);
        }
        return { ...(headers || {}) };
    }

    function getSessionLockIdentity() {
        const role = (getStore('userRole') || localStorage.getItem('userRole') || '').toLowerCase();
        const email = getStore('userEmail') || localStorage.getItem('userEmail');
        const deviceId = getStore(DEVICE_ID_KEY) || localStorage.getItem(DEVICE_ID_KEY);
        if (!email || !deviceId || !['teacher', 'admin'].includes(role)) {
            return null;
        }
        return { email, role, device_id: deviceId };
    }

    function releaseServerSessionLock(useBeacon) {
        const identity = getSessionLockIdentity();
        if (!identity) return false;
        const url = `${getBackendBase()}/auth/session/release`;
        const payload = JSON.stringify(identity);

        if (useBeacon && navigator.sendBeacon) {
            try {
                return navigator.sendBeacon(url, new Blob([payload], { type: 'application/json' }));
            } catch (_) {
            }
        }

        try {
            fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload,
                keepalive: true
            }).catch(() => {});
            return true;
        } catch (_) {
            return false;
        }
    }

    async function syncServerSessionLock() {
        /* ── TESTING MODE: lock sync disabled ── */
        if (DISABLE_SESSION_TIMEOUT) return true;

        const identity = getSessionLockIdentity();
        if (!identity) return true;

        try {
            const renewHeaders = await buildAuthHeaders({ 'Content-Type': 'application/json' });
            let response = await fetch(`${getBackendBase()}/auth/session/renew`, {
                method: 'POST',
                headers: renewHeaders,
                body: JSON.stringify(identity)
            });

            if (response.ok) {
                return true;
            }

            const acquireHeaders = await buildAuthHeaders({ 'Content-Type': 'application/json' });
            response = await fetch(`${getBackendBase()}/auth/session/acquire`, {
                method: 'POST',
                headers: acquireHeaders,
                body: JSON.stringify(identity)
            });

            if (response.ok) {
                return true;
            }

            const data = await response.json().catch(() => ({}));
            const message = data.error || 'This account is already active on another device.';
            if (/another device/i.test(message)) {
                broadcastLogout('locked');
            }
            return false;
        } catch (_) {
            return false;
        }
    }

    function redirectToLogin(reason) {
        if (!currentConfig) return;
        const destination = buildLoginUrl(currentConfig.loginUrl);
        if (reason) {
            sessionStorage.setItem('sessionLogoutReason', reason);
        }
        if (window.location.href.indexOf(destination) === -1) {
            window.location.href = destination;
        }
    }

    function broadcastLogout(reason, options) {
        const shouldReleaseLock = !options || options.releaseLock !== false;
        if (shouldReleaseLock) {
            releaseServerSessionLock(false);
        }
        localStorage.setItem(LOGOUT_BROADCAST_KEY, String(nowMs()));
        clearAuthStorage();
        redirectToLogin(reason || 'expired');
    }

    function touch(force) {
        if (!getStore('isLoggedIn')) return;
        const current = nowMs();
        if (!force && current - lastTouchAt < ACTIVITY_THROTTLE_MS) return;
        lastTouchAt = current;
        setStore(LAST_ACTIVITY_KEY, String(current));
    }

    function ensureSessionMarkers() {
        const current = nowMs();
        if (!readNumber(LOGIN_AT_KEY)) {
            setStore(LOGIN_AT_KEY, String(current));
        }
        if (!readNumber(LAST_ACTIVITY_KEY)) {
            setStore(LAST_ACTIVITY_KEY, String(current));
        }
    }

    function isExpired() {
        /* ── TESTING MODE: timeout disabled ── */
        if (DISABLE_SESSION_TIMEOUT) return false;

        const loginAt = readNumber(LOGIN_AT_KEY);
        const lastActivityAt = readNumber(LAST_ACTIVITY_KEY);
        const current = nowMs();
        const idleTimeout = currentConfig?.idleTimeoutMs || DEFAULT_IDLE_TIMEOUT_MS;
        const absoluteTimeout = currentConfig?.absoluteTimeoutMs || DEFAULT_ABSOLUTE_TIMEOUT_MS;

        if (!loginAt || !lastActivityAt) {
            return false;
        }

        if (current - loginAt >= absoluteTimeout) {
            return true;
        }

        if (current - lastActivityAt >= idleTimeout) {
            return true;
        }

        return false;
    }

    function checkSession() {
        if (!currentConfig) return true;
        /* ── TESTING MODE: always valid ── */
        if (DISABLE_SESSION_TIMEOUT) return true;
        if (!getStore('isLoggedIn')) return false;
        if (isExpired()) {
            broadcastLogout('expired');
            return false;
        }
        return true;
    }

    function bindStorageHandler() {
        if (storageHandlerBound) return;
        storageHandlerBound = true;
        window.addEventListener('storage', function (event) {
            /* ── TESTING MODE: ignore logout broadcasts ── */
            if (DISABLE_SESSION_TIMEOUT) return;
            if (event.key === LOGOUT_BROADCAST_KEY && event.newValue) {
                redirectToLogin('expired');
            }
            if (event.key === LAST_ACTIVITY_KEY && event.newValue) {
                lastTouchAt = Number(event.newValue) || lastTouchAt;
            }
        });
    }

    function bindActivityHandlers() {
        ['click', 'keydown', 'input', 'focusin', 'scroll', 'mousemove', 'touchstart'].forEach((eventName) => {
            window.addEventListener(eventName, function () {
                touch(false);
            }, { passive: true });
        });

        document.addEventListener('visibilitychange', function () {
            if (!document.hidden) {
                touch(true);
                checkSession();
            }
        });

        window.addEventListener('pagehide', function () {
            if (getStore('isLoggedIn')) {
                markPageTransition();
                releaseServerSessionLock(true);
            }
        });

        window.addEventListener('beforeunload', function () {
            if (getStore('isLoggedIn')) {
                markPageTransition();
                releaseServerSessionLock(true);
            }
        });
    }

    function startChecking() {
        /* ── TESTING MODE: no periodic checks ── */
        if (TESTING_MODE_DISABLE_TIMEOUT) return;

        if (checkTimer) {
            clearInterval(checkTimer);
        }
        checkTimer = setInterval(checkSession, CHECK_INTERVAL_MS);

        if (renewTimer) {
            clearInterval(renewTimer);
        }
        renewTimer = setInterval(function () {
            syncServerSessionLock();
        }, LOCK_RENEW_INTERVAL_MS);
    }

    window.SessionManager = {
        init: function (config) {
            currentConfig = {
                loginUrl: 'login.html',
                idleTimeoutMs: DEFAULT_IDLE_TIMEOUT_MS,
                absoluteTimeoutMs: DEFAULT_ABSOLUTE_TIMEOUT_MS,
                ...config
            };

            if (!sessionStorage.getItem('isLoggedIn')) {
                if (restoreSessionFromLocalStorage()) {
                    ensureSessionMarkers();
                    touch(true);
                    bindStorageHandler();
                    bindActivityHandlers();
                    syncServerSessionLock();
                    startChecking();
                    return checkSession();
                }
                if (localStorage.getItem('isLoggedIn')) {
                    releaseServerSessionLock(false);
                    clearAuthStorage();
                }
                if (currentConfig.requireAuth !== false) {
                    redirectToLogin('missing');
                }
                return false;
            }

            ensureSessionMarkers();
            touch(true);
            bindStorageHandler();
            bindActivityHandlers();
            syncServerSessionLock();
            startChecking();
            return checkSession();
        },
        touch: function () {
            touch(true);
        },
        logout: function (reason) {
            broadcastLogout(reason || 'manual');
        },
        clear: function () {
            clearAuthStorage();
        },
        stampLogin: function () {
            const current = nowMs();
            setStore('isLoggedIn', 'true');
            setStore(LOGIN_AT_KEY, String(current));
            setStore(LAST_ACTIVITY_KEY, String(current));
            localStorage.removeItem(LOGOUT_BROADCAST_KEY);
        },
        setAuthData: function (data) {
            Object.entries(data || {}).forEach(([key, value]) => {
                if (value === null || value === undefined || value === '') {
                    removeStore(key);
                } else {
                    setStore(key, String(value));
                }
            });
        }
    };
})();
