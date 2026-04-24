/**
 * Smart Exam System — Grok AI Chatbot Widget
 * Floating chat button on all dashboards.
 * Communicates via /api/chatbot (backend proxy — API key stays on server).
 */
(function () {
    'use strict';

    const BACKEND_BASE = window.AppConfig ? window.AppConfig.getBackendBase() : 'http://127.0.0.1:5000/api';
    let messageHistory = [];
    let isOpen = false;
    let isTyping = false;

    // ── Role-aware greeting ──────────────────────────────────────────
    function getGreeting() {
        const role = (localStorage.getItem('userRole') || 'student').toLowerCase();
        const name = localStorage.getItem('userFirstName') || localStorage.getItem('userName') || '';
        const greetName = name ? `, ${name.split(' ')[0]}` : '';
        const greetings = {
            student: `Hi${greetName}! I'm your AI study assistant. Ask me anything about your courses, exam topics, or concepts you want to understand better.`,
            teacher: `Hello${greetName}! I'm your AI teaching assistant. I can help with question design, grading guidance, or student performance analysis.`,
            admin:   `Hello${greetName}! I'm your AI system assistant. I can help with platform management, analytics, or user administration questions.`
        };
        return greetings[role] || greetings.student;
    }

    // ── Inject CSS ───────────────────────────────────────────────────
    function injectStyles() {
        if (document.getElementById('chatbot-styles')) return;
        const style = document.createElement('style');
        style.id = 'chatbot-styles';
        style.textContent = `
            /* Ensure fixed chatbot elements are never clipped */
            #chatbot-fab,
            #chatbot-window {
                position: fixed !important;
                transform: translateZ(0);
                -webkit-transform: translateZ(0);
                will-change: transform;
                pointer-events: auto !important;
            }
            #chatbot-fab {
                position: fixed !important;
                bottom: 28px !important;
                right: 28px !important;
                width: 56px;
                height: 56px;
                border-radius: 50%;
                background: linear-gradient(135deg, #4f46e5, #7c3aed);
                border: none;
                cursor: pointer;
                box-shadow: 0 8px 24px rgba(99,102,241,0.45);
                z-index: 2147483647 !important;
                display: flex !important;
                visibility: visible !important;
                opacity: 1 !important;
                align-items: center;
                justify-content: center;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
                color: #fff;
                font-size: 1.4rem;
                isolation: isolate;
            }
            #chatbot-fab:hover {
                transform: scale(1.08) translateY(-2px);
                box-shadow: 0 12px 32px rgba(99,102,241,0.55);
            }
            #chatbot-fab .fab-badge {
                position: absolute;
                top: -3px;
                right: -3px;
                width: 18px;
                height: 18px;
                background: #ef4444;
                border-radius: 50%;
                font-size: 0.65rem;
                font-weight: 800;
                display: none;
                align-items: center;
                justify-content: center;
                color: #fff;
                border: 2px solid #080321;
            }
            #chatbot-window {
                position: fixed !important;
                bottom: 96px !important;
                right: 28px !important;
                width: 380px;
                max-width: calc(100vw - 32px);
                height: 520px;
                max-height: calc(100vh - 120px);
                background: rgba(10, 8, 30, 0.97);
                border: 1px solid rgba(129,140,248,0.28);
                border-radius: 20px;
                box-shadow: 0 24px 60px rgba(0,0,0,0.55);
                z-index: 2147483646 !important;
                display: none !important;
                flex-direction: column;
                overflow: hidden;
                backdrop-filter: blur(16px);
                animation: chatSlideUp 0.25s ease;
            }
            @keyframes chatSlideUp {
                from { opacity: 0; transform: translateY(16px) scale(0.97); }
                to   { opacity: 1; transform: translateY(0)   scale(1);    }
            }
            #chatbot-window.open { display: flex !important; }
            .chat-header {
                background: linear-gradient(135deg, rgba(79,70,229,0.22), rgba(124,58,237,0.18));
                border-bottom: 1px solid rgba(129,140,248,0.2);
                padding: 14px 16px;
                display: flex;
                align-items: center;
                gap: 10px;
                flex-shrink: 0;
            }
            .chat-header-avatar {
                width: 36px;
                height: 36px;
                border-radius: 10px;
                background: linear-gradient(135deg, #4f46e5, #7c3aed);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.1rem;
                flex-shrink: 0;
            }
            .chat-header-info { flex: 1; min-width: 0; }
            .chat-header-title {
                font-size: 0.92rem;
                font-weight: 800;
                color: #f8fafc;
                line-height: 1.2;
            }
            .chat-header-sub {
                font-size: 0.72rem;
                color: #6ee7b7;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 4px;
            }
            .chat-header-sub::before {
                content: '';
                width: 6px;
                height: 6px;
                background: #10b981;
                border-radius: 50%;
                display: inline-block;
                animation: blink 2s infinite;
            }
            @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.4} }
            .chat-close-btn {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.1);
                color: #94a3b8;
                width: 30px;
                height: 30px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 1rem;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s;
                flex-shrink: 0;
            }
            .chat-close-btn:hover { background: rgba(239,68,68,0.15); color: #fca5a5; border-color: rgba(239,68,68,0.3); }
            .chat-messages {
                flex: 1;
                overflow-y: auto;
                padding: 14px 14px 8px;
                display: flex;
                flex-direction: column;
                gap: 10px;
                scroll-behavior: smooth;
            }
            .chat-messages::-webkit-scrollbar { width: 4px; }
            .chat-messages::-webkit-scrollbar-track { background: transparent; }
            .chat-messages::-webkit-scrollbar-thumb { background: rgba(129,140,248,0.3); border-radius: 999px; }
            .chat-msg {
                display: flex;
                gap: 8px;
                align-items: flex-end;
                animation: msgFadeIn 0.2s ease;
            }
            @keyframes msgFadeIn { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
            .chat-msg.user { flex-direction: row-reverse; }
            .chat-msg-avatar {
                width: 28px;
                height: 28px;
                border-radius: 8px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 0.75rem;
                font-weight: 800;
                flex-shrink: 0;
            }
            .chat-msg.bot  .chat-msg-avatar { background: linear-gradient(135deg,#4f46e5,#7c3aed); color:#fff; }
            .chat-msg.user .chat-msg-avatar { background: rgba(255,255,255,0.1); color:#94a3b8; border:1px solid rgba(255,255,255,0.1); }
            .chat-msg-bubble {
                max-width: 78%;
                padding: 10px 13px;
                border-radius: 14px;
                font-size: 0.875rem;
                line-height: 1.6;
                word-break: break-word;
            }
            .chat-msg.bot  .chat-msg-bubble {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(129,140,248,0.18);
                color: #e2e8f0;
                border-bottom-left-radius: 4px;
            }
            .chat-msg.user .chat-msg-bubble {
                background: linear-gradient(135deg, rgba(79,70,229,0.35), rgba(124,58,237,0.28));
                border: 1px solid rgba(129,140,248,0.3);
                color: #f1f5f9;
                border-bottom-right-radius: 4px;
            }
            .chat-msg-bubble p { margin: 0 0 6px; }
            .chat-msg-bubble p:last-child { margin: 0; }
            .chat-msg-bubble code {
                background: rgba(0,0,0,0.3);
                padding: 1px 5px;
                border-radius: 4px;
                font-family: monospace;
                font-size: 0.82rem;
                color: #a5b4fc;
            }
            .chat-msg-bubble pre {
                background: rgba(0,0,0,0.35);
                border: 1px solid rgba(129,140,248,0.2);
                border-radius: 8px;
                padding: 10px;
                overflow-x: auto;
                margin: 6px 0;
                font-size: 0.8rem;
            }
            .chat-msg-bubble strong { color: #c4b5fd; }
            .chat-typing {
                display: flex;
                gap: 4px;
                align-items: center;
                padding: 10px 13px;
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(129,140,248,0.18);
                border-radius: 14px;
                border-bottom-left-radius: 4px;
                width: fit-content;
            }
            .chat-typing span {
                width: 7px;
                height: 7px;
                background: #6366f1;
                border-radius: 50%;
                animation: typingDot 1.2s infinite;
            }
            .chat-typing span:nth-child(2) { animation-delay: 0.2s; }
            .chat-typing span:nth-child(3) { animation-delay: 0.4s; }
            @keyframes typingDot { 0%,60%,100%{transform:translateY(0);opacity:0.5} 30%{transform:translateY(-5px);opacity:1} }
            .chat-footer {
                padding: 10px 12px 12px;
                border-top: 1px solid rgba(129,140,248,0.15);
                flex-shrink: 0;
            }
            .chat-input-row {
                display: flex;
                gap: 8px;
                align-items: flex-end;
            }
            #chatbot-input {
                flex: 1;
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(129,140,248,0.25);
                border-radius: 12px;
                padding: 10px 13px;
                color: #f1f5f9;
                font-family: 'Manrope', sans-serif;
                font-size: 0.875rem;
                resize: none;
                min-height: 42px;
                max-height: 100px;
                line-height: 1.5;
                transition: border-color 0.2s;
                outline: none;
            }
            #chatbot-input::placeholder { color: #475569; }
            #chatbot-input:focus { border-color: rgba(99,102,241,0.55); }
            #chatbot-send {
                width: 40px;
                height: 40px;
                border-radius: 10px;
                background: linear-gradient(135deg, #4f46e5, #7c3aed);
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #fff;
                font-size: 1rem;
                flex-shrink: 0;
                transition: all 0.2s;
                box-shadow: 0 4px 12px rgba(99,102,241,0.35);
            }
            #chatbot-send:hover:not(:disabled) { transform: scale(1.05); box-shadow: 0 6px 16px rgba(99,102,241,0.5); }
            #chatbot-send:disabled { opacity: 0.45; cursor: not-allowed; transform: none; }
            .chat-footer-hint {
                font-size: 0.68rem;
                color: #475569;
                text-align: center;
                margin-top: 6px;
            }
            .chat-quick-btns {
                display: flex;
                flex-wrap: wrap;
                gap: 5px;
                margin-bottom: 8px;
            }
            .chat-quick-btn {
                background: rgba(99,102,241,0.1);
                border: 1px solid rgba(99,102,241,0.25);
                color: #a5b4fc;
                padding: 4px 10px;
                border-radius: 999px;
                font-size: 0.75rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.18s;
                font-family: 'Manrope', sans-serif;
            }
            .chat-quick-btn:hover { background: rgba(99,102,241,0.2); border-color: rgba(99,102,241,0.45); color: #c4b5fd; }
            @media (max-width: 480px) {
                #chatbot-window { right: 12px !important; bottom: 80px !important; width: calc(100vw - 24px); }
                #chatbot-fab { bottom: 16px !important; right: 16px !important; }
            }
        `;
        document.head.appendChild(style);
    }

    // ── Build HTML ───────────────────────────────────────────────────
    function buildWidget() {
        const role = (localStorage.getItem('userRole') || 'student').toLowerCase();
        const quickPrompts = {
            student: ['Explain a concept', 'Study tips', 'How to prepare?', 'What is...?'],
            teacher: ['Question ideas', 'Grading rubric', 'Teaching strategy', 'Exam design'],
            admin:   ['User management', 'System help', 'Analytics guide', 'Best practices']
        };
        const prompts = quickPrompts[role] || quickPrompts.student;

        // FAB button
        const fab = document.createElement('button');
        fab.id = 'chatbot-fab';
        fab.title = 'AI Assistant';
        fab.innerHTML = `
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <span class="fab-badge" id="chatbot-badge"></span>
        `;
        fab.addEventListener('click', toggleChat);

        // Chat window
        const win = document.createElement('div');
        win.id = 'chatbot-window';
        win.innerHTML = `
            <div class="chat-header">
                <div class="chat-header-avatar">🤖</div>
                <div class="chat-header-info">
                    <div class="chat-header-title">Grok AI Assistant</div>
                    <div class="chat-header-sub">Online — Powered by xAI</div>
                </div>
                <button class="chat-close-btn" onclick="window.__chatbotClose()" title="Close">✕</button>
            </div>
            <div class="chat-messages" id="chatbot-messages"></div>
            <div class="chat-footer">
                <div class="chat-quick-btns" id="chatbot-quick-btns">
                    ${prompts.map(p => `<button class="chat-quick-btn" onclick="window.__chatbotQuick('${p}')">${p}</button>`).join('')}
                </div>
                <div class="chat-input-row">
                    <textarea id="chatbot-input" placeholder="Ask anything..." rows="1"></textarea>
                    <button id="chatbot-send" onclick="window.__chatbotSend()" title="Send">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
                        </svg>
                    </button>
                </div>
                <div class="chat-footer-hint">Grok AI · Smart Exam System</div>
            </div>
        `;

        document.body.appendChild(fab);
        document.body.appendChild(win);

        // Auto-resize textarea
        const input = document.getElementById('chatbot-input');
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 100) + 'px';
        });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                window.__chatbotSend();
            }
        });

        // Show greeting
        addMessage('bot', getGreeting());
    }

    // ── Toggle open/close ────────────────────────────────────────────
    function toggleChat() {
        isOpen = !isOpen;
        const win = document.getElementById('chatbot-window');
        const badge = document.getElementById('chatbot-badge');
        if (isOpen) {
            win.classList.add('open');
            badge.style.display = 'none';
            setTimeout(() => document.getElementById('chatbot-input')?.focus(), 100);
        } else {
            win.classList.remove('open');
        }
    }

    window.__chatbotClose = () => { isOpen = true; toggleChat(); };

    // ── Add message to UI ────────────────────────────────────────────
    function addMessage(role, text) {
        const container = document.getElementById('chatbot-messages');
        if (!container) return;

        const initials = role === 'bot' ? 'AI' : (localStorage.getItem('userFirstName') || 'U').charAt(0).toUpperCase();
        const div = document.createElement('div');
        div.className = `chat-msg ${role}`;

        // Convert markdown-like formatting
        const formatted = text
            .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');

        div.innerHTML = `
            <div class="chat-msg-avatar">${initials}</div>
            <div class="chat-msg-bubble"><p>${formatted}</p></div>
        `;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;

        // Show badge if closed
        if (!isOpen && role === 'bot') {
            const badge = document.getElementById('chatbot-badge');
            if (badge) { badge.style.display = 'flex'; badge.textContent = '1'; }
        }
    }

    // ── Show typing indicator ────────────────────────────────────────
    function showTyping() {
        const container = document.getElementById('chatbot-messages');
        if (!container) return;
        const div = document.createElement('div');
        div.className = 'chat-msg bot';
        div.id = 'chatbot-typing';
        div.innerHTML = `
            <div class="chat-msg-avatar">AI</div>
            <div class="chat-typing"><span></span><span></span><span></span></div>
        `;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    function hideTyping() {
        document.getElementById('chatbot-typing')?.remove();
    }

    // ── Send message ─────────────────────────────────────────────────
    window.__chatbotSend = async function () {
        if (isTyping) return;
        const input = document.getElementById('chatbot-input');
        const sendBtn = document.getElementById('chatbot-send');
        const text = (input?.value || '').trim();
        if (!text) return;

        // Hide quick buttons after first message
        const quickBtns = document.getElementById('chatbot-quick-btns');
        if (quickBtns) quickBtns.style.display = 'none';

        input.value = '';
        input.style.height = 'auto';
        addMessage('user', text);

        messageHistory.push({ role: 'user', content: text });
        isTyping = true;
        if (sendBtn) sendBtn.disabled = true;
        showTyping();

        try {
            const headers = { 'Content-Type': 'application/json' };
            // Add role header directly from localStorage — no auth token needed
            const role = (localStorage.getItem('userRole') || 'student').toLowerCase();
            const uid  = localStorage.getItem('userId');
            headers['X-User-Role'] = role;
            if (uid) headers['X-User-ID'] = uid;

            // Try to add auth token if supabase client is available
            try {
                if (window.AppConfig && window.supabaseClient) {
                    const token = await window.AppConfig.getAccessToken(window.supabaseClient);
                    if (token) headers['Authorization'] = `Bearer ${token}`;
                } else if (window.AppConfig) {
                    // Read token directly from localStorage without supabase client
                    const token = window.AppConfig.getAccessToken ? await window.AppConfig.getAccessToken(null) : null;
                    if (token) headers['Authorization'] = `Bearer ${token}`;
                }
            } catch (_) { /* auth optional for chatbot */ }

            const resp = await fetch(`${BACKEND_BASE}/chatbot`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ messages: messageHistory, role })
            });

            hideTyping();

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.error || `Server error ${resp.status}`);
            }

            const data = await resp.json();
            const reply = data.reply || 'Sorry, I could not generate a response.';
            messageHistory.push({ role: 'assistant', content: reply });
            addMessage('bot', reply);

        } catch (err) {
            hideTyping();
            addMessage('bot', `Sorry, I encountered an error: ${err.message}. Please try again.`);
        } finally {
            isTyping = false;
            if (sendBtn) sendBtn.disabled = false;
            input?.focus();
        }
    };

    window.__chatbotQuick = function (prompt) {
        const input = document.getElementById('chatbot-input');
        if (input) { input.value = prompt; input.focus(); }
        window.__chatbotSend();
    };

    // ── Init ─────────────────────────────────────────────────────────
    function init() {
        // Only show on dashboard pages (not login/signup/take-exam)
        const path = window.location.pathname.toLowerCase();
        const excluded = ['login', 'signup', 'take-exam', 'reset-password', 'index'];
        if (excluded.some(p => path.includes(p))) return;
        if (window.self !== window.top) return;

        injectStyles();
        buildWidget();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
