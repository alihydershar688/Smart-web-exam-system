;(function () {
    if (window.MobileNav) return

    const STYLE_ID = 'mobile-nav-styles'

    function ensureStyles() {
        if (document.getElementById(STYLE_ID)) return
        const style = document.createElement('style')
        style.id = STYLE_ID
        style.textContent = `
            .mobile-nav-actions {
                display: none;
                align-items: center;
                gap: 0.6rem;
                margin-left: auto;
            }

            .mobile-icon-btn {
                width: 40px;
                height: 40px;
                border-radius: 12px;
                border: 1px solid rgba(148, 163, 184, 0.24);
                background: rgba(255, 255, 255, 0.72);
                color: #0f172a;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                font-size: 1rem;
                transition: transform 0.2s ease, background 0.2s ease;
            }

            .mobile-icon-btn:hover {
                transform: translateY(-1px);
                background: #ffffff;
            }

            .mobile-nav-drawer {
                position: fixed;
                inset: 0;
                z-index: 1500;
                pointer-events: none;
                visibility: hidden;
                opacity: 0;
                transition: opacity 0.2s ease, visibility 0.2s ease;
            }

            .mobile-nav-backdrop {
                position: absolute;
                inset: 0;
                background: rgba(2, 6, 23, 0.56);
                opacity: 0;
                transition: opacity 0.25s ease;
            }

            .mobile-nav-panel {
                position: absolute;
                top: 0;
                left: 0;
                width: min(320px, 86vw);
                height: 100%;
                background: linear-gradient(180deg, #0f172a 0%, #12243f 100%);
                color: #f8fafc;
                border-right: 1px solid rgba(148, 163, 184, 0.18);
                box-shadow: 0 18px 44px rgba(2, 6, 23, 0.35);
                transform: translateX(-100%);
                transition: transform 0.28s ease;
                display: flex;
                flex-direction: column;
            }

            .mobile-nav-drawer.open {
                pointer-events: auto;
                visibility: visible;
                opacity: 1;
            }

            .mobile-nav-drawer.open .mobile-nav-backdrop {
                opacity: 1;
            }

            .mobile-nav-drawer.open .mobile-nav-panel {
                transform: translateX(0);
            }

            .mobile-nav-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 1rem;
                padding: 1rem 1rem 0.95rem;
                border-bottom: 1px solid rgba(148, 163, 184, 0.18);
            }

            .mobile-nav-brand {
                font-weight: 800;
                color: #f8fafc;
                line-height: 1.25;
            }

            .mobile-nav-close {
                width: 38px;
                height: 38px;
                border-radius: 10px;
                border: 1px solid rgba(148, 163, 184, 0.18);
                background: rgba(255, 255, 255, 0.06);
                color: #f8fafc;
                cursor: pointer;
                font-size: 1rem;
            }

            .mobile-nav-list,
            .mobile-nav-footer {
                display: grid;
                gap: 0.35rem;
                padding: 1rem;
            }

            .mobile-nav-footer {
                margin-top: auto;
                border-top: 1px solid rgba(148, 163, 184, 0.18);
            }

            .mobile-nav-link,
            .mobile-nav-action {
                display: flex;
                align-items: center;
                justify-content: space-between;
                text-decoration: none;
                color: #e2e8f0;
                padding: 0.85rem 0.95rem;
                border-radius: 12px;
                border: 1px solid transparent;
                background: rgba(255, 255, 255, 0.02);
                font-weight: 700;
                transition: background 0.2s ease, border-color 0.2s ease;
            }

            .mobile-nav-link:hover,
            .mobile-nav-action:hover {
                background: rgba(20, 184, 166, 0.12);
                border-color: rgba(94, 234, 212, 0.22);
            }

            .mobile-nav-muted {
                color: #94a3b8;
                font-size: 0.8rem;
                font-weight: 600;
            }

            body.mobile-nav-open {
                overflow: hidden;
            }

            @media (max-width: 900px) {
                .mobile-nav-actions {
                    display: inline-flex;
                }
            }
        `
        document.head.appendChild(style)
    }

    function buildDrawer(config) {
        const drawer = document.createElement('div')
        drawer.className = 'mobile-nav-drawer'

        const primaryItems = (config.items || []).map(item => `
            <a class="mobile-nav-link" href="${item.href || '#'}" ${item.onclick ? `data-onclick="${item.onclick}"` : ''}>
                <span>${item.label}</span>
                <span class="mobile-nav-muted">${item.meta || ''}</span>
            </a>
        `).join('')

        drawer.innerHTML = `
            <div class="mobile-nav-backdrop" data-mobile-close></div>
            <aside class="mobile-nav-panel" aria-label="Mobile navigation">
                <div class="mobile-nav-header">
                    <div class="mobile-nav-brand">${config.brand || 'Smart Exam System'}</div>
                    <button type="button" class="mobile-nav-close" data-mobile-close>&times;</button>
                </div>
                <div class="mobile-nav-list">
                    ${primaryItems}
                </div>
                <div class="mobile-nav-footer">
                    <a class="mobile-nav-link" href="${config.profileHref || '#'}">
                        <span>Profile</span>
                        <span class="mobile-nav-muted">Account</span>
                    </a>
                    <button type="button" class="mobile-nav-action" data-mobile-logout>
                        <span>Logout</span>
                        <span class="mobile-nav-muted">Exit</span>
                    </button>
                </div>
            </aside>
        `

        return drawer
    }

    function attachActions(container, config, drawer) {
        const actions = document.createElement('div')
        actions.className = 'mobile-nav-actions'
        actions.innerHTML = `
            <button type="button" class="mobile-icon-btn" data-mobile-open aria-label="Open navigation">&#9776;</button>
            <button type="button" class="mobile-icon-btn" aria-label="Notifications">&#128276;</button>
            <button type="button" class="mobile-icon-btn" aria-label="Profile">&#128100;</button>
        `
        container.appendChild(actions)

        const openBtn = actions.querySelector('[data-mobile-open]')
        const closeEls = drawer.querySelectorAll('[data-mobile-close]')
        const logoutBtn = drawer.querySelector('[data-mobile-logout]')

        function openDrawer() {
            drawer.classList.add('open')
            document.body.classList.add('mobile-nav-open')
        }

        function closeDrawer() {
            drawer.classList.remove('open')
            document.body.classList.remove('mobile-nav-open')
        }

        closeDrawer()

        openBtn.addEventListener('click', openDrawer)
        closeEls.forEach(el => el.addEventListener('click', closeDrawer))
        logoutBtn.addEventListener('click', function () {
            closeDrawer()
            if (typeof config.onLogout === 'function') {
                config.onLogout()
            }
        })

        drawer.querySelectorAll('[data-onclick]').forEach(el => {
            el.addEventListener('click', function (event) {
                const fnName = el.getAttribute('data-onclick')
                if (fnName && typeof window[fnName] === 'function') {
                    event.preventDefault()
                    closeDrawer()
                    window[fnName]()
                }
            })
        })

        window.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeDrawer()
            }
        })

        window.addEventListener('resize', function () {
            if (window.innerWidth > 900) {
                closeDrawer()
            }
        })
    }

    window.MobileNav = {
        init: function (config) {
            ensureStyles()
            document.body.classList.remove('mobile-nav-open')
            document.querySelectorAll('.mobile-nav-drawer').forEach(function (drawer) {
                drawer.classList.remove('open')
                drawer.remove()
            })
            const target = document.querySelector(config.targetSelector)
            if (!target) return
            const drawer = buildDrawer(config)
            document.body.appendChild(drawer)
            attachActions(target, config, drawer)
        }
    }
})()
