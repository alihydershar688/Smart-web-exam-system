(function () {
    const COLLAPSE_KEY = 'appShellSidebarCollapsed';
    const MOBILE_QUERY = '(max-width: 1024px)';
    let navObserver = null;

    function isSimpleSidebar() {
        return document.body.classList.contains('sidebar-simple');
    }

    function supportsSimpleSidebarIcons() {
        return isSimpleSidebar();
    }

    function supportsDesktopCollapse() {
        return document.body.classList.contains('teacher-shell-page');
    }

    function ensureShellOverrides() {
        if (document.getElementById('app-shell-final-overrides')) return;
        const style = document.createElement('style');
        style.id = 'app-shell-final-overrides';
        style.textContent = '';
        document.head.appendChild(style);
    }

    function isMobile() {
        return window.matchMedia(MOBILE_QUERY).matches;
    }

    function getSidebar() {
        return document.querySelector('.sidebar, .workspace-sidebar');
    }

    function getNav() {
        return document.querySelector('.sidebar-nav, .workspace-sidebar-nav');
    }

    function getToggles(selector) {
        return selector
            ? document.querySelectorAll(selector)
            : document.querySelectorAll('[data-sidebar-toggle]');
    }

    function syncToggleState(selector) {
        const expanded = isMobile()
            ? document.body.classList.contains('sidebar-drawer-open')
            : !document.body.classList.contains('sidebar-collapsed');
        getToggles(selector).forEach((button) => {
            button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        });
    }

    function getFooter() {
        return document.querySelector('.sidebar-footer, .workspace-sidebar-footer');
    }

    function getStoredRole() {
        const role = (sessionStorage.getItem('userRole') || localStorage.getItem('userRole') || '').toLowerCase();
        if (role === 'teacher' || role === 'student' || role === 'admin') return role;
        return '';
    }

    function getBrandHref() {
        const role = getStoredRole();
        if (role === 'teacher' || role === 'student' || role === 'admin') return 'profile.html';
        return 'index.html';
    }

    function syncHomeLinks() {
        const href = getBrandHref();
        document.querySelectorAll('a.logo, a.workspace-logo').forEach((link) => {
            if (!link.dataset.staticHome) {
                link.setAttribute('href', href);
                link.setAttribute('title', href === 'profile.html' ? 'Open profile' : 'Go to home');
            }
        });
    }

    function getPageLabel() {
        const candidate = document.querySelector('.workspace-brand-page, .brand-page');
        if (candidate && candidate.textContent.trim()) {
            return candidate.textContent.trim();
        }
        const rawTitle = (document.title || '').split('|')[0].trim();
        return rawTitle || 'Dashboard';
    }

    function normalizeHeaderBrand() {
        const group = document.querySelector('.header-brand-group');
        if (!group) return;

        const isWorkspace = !!document.querySelector('.workspace-topbar, .workspace-sidebar');
        const pageLabel = getPageLabel();
        const href = getBrandHref();
        const toggle = group.querySelector('.shell-toggle');
        const existing = group.querySelector('.workspace-logo, .brand, .brand-wrap, .logo');
        if (!existing) return;
        const existingId = existing.id || (existing.querySelector && existing.querySelector('[id]') ? existing.querySelector('[id]').id : '');
        const staticHome = existing.dataset ? existing.dataset.staticHome : '';

        const wrapper =
            existing.classList.contains('brand-wrap')
                ? existing
                : existing.closest('.brand-wrap') || existing.closest('.brand') || existing;

        const brand = document.createElement('a');
        brand.href = href;
        brand.setAttribute('title', href === 'profile.html' ? 'Open profile' : 'Go to home');
        if (existingId) {
            brand.id = existingId;
        }
        if (staticHome) {
            brand.dataset.staticHome = staticHome;
        }

        if (isWorkspace) {
            brand.className = 'workspace-logo';
            brand.innerHTML = `
                <span class="workspace-brand-mark">SE</span>
                <span class="workspace-brand-copy">
                    <span class="workspace-brand-name">Smart Exam System</span>
                    <span class="workspace-brand-page">${pageLabel}</span>
                </span>
            `;
        } else {
            brand.className = 'brand';
            brand.innerHTML = `
                <span class="brand-mark">SE</span>
                <span class="brand-copy">
                    <span class="brand-name">Smart Exam System</span>
                    <span class="brand-page">${pageLabel}</span>
                </span>
            `;
        }

        if (wrapper && wrapper !== group) {
            wrapper.remove();
        }

        if (toggle) {
            toggle.insertAdjacentElement('afterend', brand);
        } else {
            group.prepend(brand);
        }
    }

    function buildProfileNavItem(isWorkspace, href, active) {
        const link = document.createElement('a');
        link.href = href || 'profile.html';
        link.className = `${isWorkspace ? 'workspace-sidebar-link' : 'sidebar-link'}${active ? ' active' : ''}`;
        link.setAttribute('data-shell-generated', 'profile');
        if (isSimpleSidebar()) {
            link.innerHTML = isWorkspace
                ? `
                    <span class="workspace-sidebar-link-main">
                        <span class="workspace-sidebar-link-copy">
                            <span class="workspace-sidebar-link-title">Profile</span>
                            <span class="workspace-sidebar-link-desc"></span>
                        </span>
                    </span>
                `
                : `
                    <span class="sidebar-link-main">
                        <span class="sidebar-link-copy">
                            <span class="sidebar-link-title">Profile</span>
                            <span class="sidebar-link-desc"></span>
                        </span>
                    </span>
                `;
            return link;
        }
        link.innerHTML = isWorkspace
            ? `
                <span class="workspace-sidebar-link-main">
                    <span class="workspace-sidebar-link-icon">PF</span>
                    <span class="workspace-sidebar-link-copy">
                        <span class="workspace-sidebar-link-title">Profile</span>
                        <span class="workspace-sidebar-link-desc"></span>
                    </span>
                </span>
            `
            : `
                <span class="sidebar-link-main">
                    <span class="sidebar-link-icon">PF</span>
                    <span class="sidebar-link-copy">
                        <span class="sidebar-link-title">Profile</span>
                        <span class="sidebar-link-desc"></span>
                    </span>
                </span>
            `;
        return link;
    }

    function simplifySidebarNav() {
        document.querySelectorAll('.sidebar-link, .workspace-sidebar-link').forEach((link) => {
            link.querySelectorAll('.sidebar-link-desc, .workspace-sidebar-link-desc').forEach((node) => node.remove());
            Array.from(link.children).forEach((child) => {
                const isMain =
                    child.classList.contains('sidebar-link-main') ||
                    child.classList.contains('workspace-sidebar-link-main');
                if (!isMain && child.tagName === 'SPAN') {
                    child.remove();
                }
            });
        });
    }

    function applySidebarPresentation() {
        const collapsed = !isMobile() && document.body.classList.contains('sidebar-collapsed');
        const simple = isSimpleSidebar();
        const simpleWithIcons = simple && supportsSimpleSidebarIcons();

        document.querySelectorAll('.sidebar-link, .workspace-sidebar-link').forEach((link) => {
            const main = link.querySelector('.sidebar-link-main, .workspace-sidebar-link-main');
            const icon = link.querySelector('.sidebar-link-icon, .workspace-sidebar-link-icon');
            const copy = link.querySelector('.sidebar-link-copy, .workspace-sidebar-link-copy');
            const title = link.querySelector('.sidebar-link-title, .workspace-sidebar-link-title');

            link.style.justifyContent = collapsed ? 'center' : 'flex-start';
            link.style.alignItems = 'center';
            link.style.minHeight = '56px';

            if (main) {
                main.style.display = 'flex';
                main.style.alignItems = 'center';
                main.style.justifyContent = collapsed ? 'center' : 'flex-start';
                main.style.gap = collapsed ? '0' : (simpleWithIcons ? '10px' : (simple ? '0' : '14px'));
                main.style.width = '100%';
            }

            if (icon) {
                if (simple && !simpleWithIcons) {
                    icon.style.display = 'none';
                } else {
                    icon.style.display = 'inline-flex';
                    icon.style.alignItems = 'center';
                    icon.style.justifyContent = 'center';
                    icon.style.opacity = '1';
                    icon.style.visibility = 'visible';
                }
            }

            if (copy) {
                copy.style.display = collapsed ? 'none' : 'block';
                copy.style.opacity = '1';
                copy.style.visibility = 'visible';
            }

            if (title) {
                title.style.display = 'block';
                title.style.opacity = '1';
                title.style.visibility = 'visible';
            }
        });

        document.querySelectorAll('.sidebar-footer-link, .sidebar-footer-button, .workspace-sidebar-footer-link, .workspace-sidebar-footer-button').forEach((item) => {
            const spans = item.querySelectorAll('span');
            const icon = spans.length > 1 ? spans[0] : null;
            const label = spans.length > 1 ? spans[1] : spans[0] || null;
            item.style.justifyContent = collapsed ? 'center' : 'flex-start';
            item.style.gap = collapsed ? '0' : (simpleWithIcons ? '10px' : (simple ? '0' : '12px'));
            if (simple) {
                if (icon) {
                    icon.style.display = simpleWithIcons || collapsed ? 'inline-flex' : 'none';
                    icon.style.alignItems = 'center';
                    icon.style.justifyContent = 'center';
                }
                if (label) {
                    label.style.display = collapsed && icon ? 'none' : 'inline';
                }
                return;
            }
            if (spans[0]) {
                spans[0].style.display = 'inline-flex';
                spans[0].style.alignItems = 'center';
                spans[0].style.justifyContent = 'center';
            }
            if (spans[1]) {
                spans[1].style.display = collapsed ? 'none' : 'inline';
            }
        });
    }

    function applyPageSpecificLayout() {
        const path = (window.location.pathname || '').toLowerCase();
        if (!path.endsWith('/profile.html') && !path.endsWith('profile.html')) return;

        const sidebar = getSidebar();
        const shell = document.querySelector('.app-shell, .workspace-shell');
        const content = document.querySelector('.content-column');

        if (sidebar) {
            sidebar.style.display = 'none';
        }
        if (shell) {
            shell.style.display = 'block';
        }
        if (content) {
            content.style.maxWidth = '1240px';
            content.style.margin = '0 auto';
        }
        getToggles().forEach((button) => {
            button.style.display = 'none';
        });
    }

    function bindNavObserver() {
        const nav = getNav();
        if (!nav) return;
        if (navObserver) {
            navObserver.disconnect();
        }
        let frameQueued = false;
        navObserver = new MutationObserver(() => {
            if (frameQueued) return;
            frameQueued = true;
            window.requestAnimationFrame(() => {
                frameQueued = false;
                simplifySidebarNav();
                applySidebarPresentation();
                syncTitles();
            });
        });
        navObserver.observe(nav, { childList: true, subtree: true });
    }

    function promoteProfileLink() {
        if (isSimpleSidebar()) return;

        const nav = getNav();
        const footer = getFooter();
        if (!nav || !footer) return;

        const profileFooterLink = footer.querySelector('.sidebar-footer-link[href*="profile.html"], .workspace-sidebar-footer-link[href*="profile.html"]');
        if (!profileFooterLink) return;

        const existingProfileNav = nav.querySelector('a[href*="profile.html"]');
        const href = profileFooterLink.getAttribute('href') || 'profile.html';
        const active = /(^|\/)profile\.html$/i.test(window.location.pathname || '') || window.location.href.toLowerCase().includes('profile.html');
        const isWorkspace = nav.classList.contains('workspace-sidebar-nav');

        if (!existingProfileNav) {
            nav.appendChild(buildProfileNavItem(isWorkspace, href, active));
        } else if (active) {
            existingProfileNav.classList.add('active');
        }

        profileFooterLink.remove();
    }

    function getOverlay() {
        let overlay = document.querySelector('.app-shell-overlay');
        if (!overlay) {
            overlay = document.createElement('button');
            overlay.type = 'button';
            overlay.className = 'app-shell-overlay';
            overlay.setAttribute('aria-label', 'Close sidebar');
            document.body.appendChild(overlay);
        }
        return overlay;
    }

    function applyCollapsed(collapsed) {
        document.body.classList.toggle('sidebar-collapsed', !!collapsed);
        localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
        applySidebarPresentation();
        syncToggleState();
    }

    function closeDrawer() {
        document.body.classList.remove('sidebar-drawer-open');
        syncToggleState();
    }

    function openDrawer() {
        document.body.classList.add('sidebar-drawer-open');
        syncToggleState();
    }

    function toggleSidebar() {
        if (!getSidebar()) return;
        if (isMobile()) {
            document.body.classList.contains('sidebar-drawer-open') ? closeDrawer() : openDrawer();
            return;
        }
        if (!supportsDesktopCollapse()) {
            applyCollapsed(false);
            return;
        }
        applyCollapsed(!document.body.classList.contains('sidebar-collapsed'));
    }

    function syncTitles() {
        document.querySelectorAll('.sidebar-link, .workspace-sidebar-link').forEach((link) => {
            const title = link.querySelector('.sidebar-link-title, .workspace-sidebar-link-title');
            if (title && !link.getAttribute('title')) {
                link.setAttribute('title', title.textContent.trim());
            }
        });
        document.querySelectorAll('.sidebar-footer-link, .workspace-sidebar-footer-link, .sidebar-footer-button, .workspace-sidebar-footer-button, .header-profile-trigger').forEach((item) => {
            if (!item.getAttribute('title')) {
                const text = item.textContent.replace(/\s+/g, ' ').trim();
                if (text) item.setAttribute('title', text);
            }
        });
    }

    function syncForViewport() {
        if (isMobile()) {
            document.body.classList.remove('sidebar-collapsed');
            closeDrawer();
            applySidebarPresentation();
            return;
        }
        closeDrawer();
        if (!supportsDesktopCollapse()) {
            applyCollapsed(false);
            applySidebarPresentation();
            return;
        }
        applyCollapsed(localStorage.getItem(COLLAPSE_KEY) === '1');
        applySidebarPresentation();
    }

    function init(options) {
        const sidebar = getSidebar();
        if (!sidebar) return;

        const config = options || {};
        document.body.classList.add('has-app-shell');

        const overlay = getOverlay();
        overlay.addEventListener('click', closeDrawer);

        const toggleTargets = config.toggleSelector
            ? getToggles(config.toggleSelector)
            : getToggles();

        toggleTargets.forEach((button) => {
            button.addEventListener('click', toggleSidebar);
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeDrawer();
            }
        });

        window.addEventListener('resize', syncForViewport);

        const footer = getFooter();
        if (footer) {
            footer.classList.add('is-ready');
        }

        ensureShellOverrides();
        syncHomeLinks();
        normalizeHeaderBrand();
        promoteProfileLink();
        simplifySidebarNav();
        applySidebarPresentation();
        applyPageSpecificLayout();
        bindNavObserver();
        syncTitles();
        syncForViewport();
        syncToggleState(config.toggleSelector);
    }

    function refresh() {
        ensureShellOverrides();
        syncHomeLinks();
        normalizeHeaderBrand();
        promoteProfileLink();
        simplifySidebarNav();
        applySidebarPresentation();
        applyPageSpecificLayout();
        bindNavObserver();
        syncTitles();
        syncToggleState();
    }

    window.AppShell = {
        init,
        refresh,
        toggleSidebar,
        openDrawer,
        closeDrawer
    };
})();
