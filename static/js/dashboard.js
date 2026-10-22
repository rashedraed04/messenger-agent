/**
 * Dashboard — Minimal Vanilla JS
 * Handles: toast notifications, confirm dialogs, sidebar toggle, CSRF token.
 * No framework dependencies.
 */

// ---------------------------------------------------------------------------
// Toast Notifications
// ---------------------------------------------------------------------------
function showToast(message, type = 'success') {
    const container = document.querySelector('.toast-container') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-bg-${type} border-0 show`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto"
                    data-bs-dismiss="toast" aria-label="إغلاق"></button>
        </div>
    `;
    container.appendChild(toast);

    // Auto-dismiss after 4 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
    return container;
}


// ---------------------------------------------------------------------------
// Confirm Dialogs
// ---------------------------------------------------------------------------
function confirmAction(message, formId) {
    if (confirm(message)) {
        document.getElementById(formId).submit();
    }
}


// ---------------------------------------------------------------------------
// Sidebar Toggle (Mobile)
// ---------------------------------------------------------------------------
function toggleSidebar(force) {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    const open = typeof force === 'boolean' ? force : !sidebar.classList.contains('show');
    sidebar.classList.toggle('show', open);
    document.body.classList.toggle('sidebar-open', open);

    const backdrop = document.getElementById('sidebar-backdrop');
    if (backdrop) backdrop.hidden = !open;
    const toggle = document.getElementById('btn-toggle-sidebar');
    if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
}

// Close the mobile menu with Escape
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') toggleSidebar(false);
});


// ---------------------------------------------------------------------------
// Light / Dark Theme Toggle (initial theme is applied inline in base.html <head>)
// ---------------------------------------------------------------------------
function updateThemeButton() {
    const btn = document.getElementById('btn-theme-toggle');
    if (!btn) return;
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    btn.textContent = isLight ? '🌙 الوضع الداكن' : '☀️ الوضع الفاتح';
}

function toggleTheme() {
    const root = document.documentElement;
    const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    if (next === 'light') {
        root.setAttribute('data-theme', 'light');
    } else {
        root.removeAttribute('data-theme');
    }
    root.setAttribute('data-bs-theme', next);
    try { localStorage.setItem('theme', next); } catch (e) {}
    updateThemeButton();
}


// ---------------------------------------------------------------------------
// CSRF token (sent as X-CSRF-Token header on fetch POSTs)
// ---------------------------------------------------------------------------
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}


// ---------------------------------------------------------------------------
// Auto-flash messages from server
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function() {
    updateThemeButton();

    // Display any flash messages rendered by Jinja2
    const flashMessages = document.querySelectorAll('[data-flash-message]');
    flashMessages.forEach(function(el) {
        showToast(el.dataset.flashMessage, el.dataset.flashType || 'success');
        el.remove();
    });
});
