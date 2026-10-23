/**
 * Storefront — live search and type/category filtering without page reloads.
 * Fetches the server-rendered results fragment from /partials/products and
 * swaps it into #results. Without JS, the plain form and links still work.
 */

(function () {
    const ALL = 'الكل';
    const DEBOUNCE_MS = 300;

    const form = document.getElementById('searchForm');
    const searchInput = document.getElementById('searchInput');
    const results = document.getElementById('results');
    const announcer = document.getElementById('resultsAnnouncer');
    if (!form || !searchInput || !results) return;

    // Each filter row: pills carry data-filter="<param>" and data-value
    const filters = {
        type: document.getElementById('typeInput'),
        category: document.getElementById('categoryInput'),
    };
    const pillGroups = document.querySelectorAll('[data-filter-group]');

    let typingTimer = null;
    let controller = null;
    let lastQueryString = currentQueryString();

    function currentQueryString() {
        const params = new URLSearchParams();
        const q = searchInput.value.trim();
        if (q) params.set('q', q);
        Object.keys(filters).forEach(function (name) {
            const input = filters[name];
            if (input && input.value && input.value !== ALL) params.set(name, input.value);
        });
        return params.toString();
    }

    function updatePills() {
        const base = new URLSearchParams(currentQueryString());
        pillGroups.forEach(function (group) {
            const name = group.dataset.filterGroup;
            const selected = (filters[name] && filters[name].value) || ALL;
            group.querySelectorAll('[data-value]').forEach(function (pill) {
                const value = pill.dataset.value;
                const active = value === selected;
                pill.classList.toggle('active', active);
                if (active) pill.setAttribute('aria-current', 'true');
                else pill.removeAttribute('aria-current');
                const params = new URLSearchParams(base);
                if (value === ALL) params.delete(name); else params.set(name, value);
                const qs = params.toString();
                pill.href = qs ? '/?' + qs : '/';
            });
        });
    }

    async function refresh() {
        const qs = currentQueryString();
        if (qs === lastQueryString) return;
        lastQueryString = qs;

        if (controller) controller.abort();
        controller = new AbortController();
        results.classList.add('is-loading');

        try {
            const resp = await fetch('/partials/products' + (qs ? '?' + qs : ''), {
                signal: controller.signal,
                headers: { 'Accept': 'text/html' },
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            results.innerHTML = await resp.text();
            // The swapped fragment can't announce itself; a persistent live region can
            const summary = results.querySelector('[data-results-summary]');
            if (announcer && summary) announcer.textContent = summary.dataset.resultsSummary;
            results.dispatchEvent(new CustomEvent('storefront:results-updated', { bubbles: true }));
            history.replaceState(null, '', qs ? '/?' + qs : '/');
            results.classList.remove('is-loading');
        } catch (err) {
            if (err.name === 'AbortError') return;
            // Fall back to a normal page load if the fragment request fails
            window.location.href = qs ? '/?' + qs : '/';
        }
    }

    searchInput.addEventListener('input', function () {
        clearTimeout(typingTimer);
        typingTimer = setTimeout(function () {
            updatePills();
            refresh();
        }, DEBOUNCE_MS);
    });

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        clearTimeout(typingTimer);
        updatePills();
        refresh();
    });

    pillGroups.forEach(function (group) {
        group.addEventListener('click', function (e) {
            const pill = e.target.closest('[data-value]');
            if (!pill || e.ctrlKey || e.metaKey || e.shiftKey) return;
            e.preventDefault();
            const input = filters[group.dataset.filterGroup];
            if (input) input.value = pill.dataset.value;
            updatePills();
            refresh();
        });
    });

    results.addEventListener('click', function (e) {
        const reset = e.target.closest('[data-reset-filters]');
        if (!reset || e.ctrlKey || e.metaKey || e.shiftKey) return;
        e.preventDefault();
        searchInput.value = '';
        Object.keys(filters).forEach(function (name) {
            if (filters[name]) filters[name].value = ALL;
        });
        updatePills();
        refresh();
        searchInput.focus();
    });
})();
