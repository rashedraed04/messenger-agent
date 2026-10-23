/**
 * Storefront motion and scroll behaviour. Nothing here hides content by
 * default: every pending state is added by this script, so the page reads
 * fine without it. Scroll-linked effects (header shade, hero recede, pill-row
 * edge fades) live in CSS on scroll timelines and need no JavaScript.
 */

(function () {
    // iOS Safari only applies :active (press feedback) when a touch listener exists
    document.addEventListener('touchstart', function () {}, { passive: true });

    /* ---- Product image continuity: name only the card being opened ---- */

    // Naming every card would make each navigation snapshot the whole grid
    document.addEventListener('click', function (e) {
        if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
        const link = e.target.closest('.perfume-card a[href^="/perfume/"]');
        if (!link) return;
        const well = link.closest('.perfume-card').querySelector('[data-vt]');
        if (well) well.style.viewTransitionName = well.dataset.vt;
    });

    // Back/forward cache restores the page with the name still set
    window.addEventListener('pageshow', function (e) {
        if (!e.persisted) return;
        document.querySelectorAll('[data-vt]').forEach(function (el) {
            el.style.viewTransitionName = '';
        });
    });

    /* ---- Sticky order bar on product pages (phones; hidden by CSS on desktop) ---- */

    const stickyCta = document.getElementById('stickyCta');
    const ctaAnchor = document.querySelector('[data-sticky-cta-anchor]');
    if (stickyCta && ctaAnchor && 'IntersectionObserver' in window) {
        const stickyLink = stickyCta.querySelector('a');
        document.body.classList.add('has-sticky-cta');
        new IntersectionObserver(function (entries) {
            const entry = entries[0];
            // Show only once the main button has scrolled away above the viewport
            const show = !entry.isIntersecting && entry.boundingClientRect.top < 0;
            stickyCta.classList.toggle('is-visible', show);
            stickyCta.setAttribute('aria-hidden', show ? 'false' : 'true');
            if (stickyLink) stickyLink.tabIndex = show ? 0 : -1;
        }).observe(ctaAnchor);
    }

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reducedMotion || !('IntersectionObserver' in window)) return;

    /* ---- Photos fade in once decoded instead of popping in ---- */

    function settlePhotos(root) {
        root.querySelectorAll('.perfume-card .product-photo').forEach(function (img) {
            if (img.complete) return;
            img.classList.add('photo-pending');
            function done() { img.classList.remove('photo-pending'); }
            img.addEventListener('load', done, { once: true });
            img.addEventListener('error', done, { once: true });
        });
    }

    /* ---- Grid reveal: cards below the fold rise in as they arrive, once ---- */

    const STAGGER_MS = 60;
    const MAX_STAGGER_STEPS = 3;
    // Covers the 450ms rise plus the crown hairline drawing in after it
    const REVEAL_CLEANUP_MS = 900;

    const observer = new IntersectionObserver(function (entries) {
        const entering = entries
            .filter(function (entry) { return entry.isIntersecting; })
            .sort(function (a, b) {
                return a.boundingClientRect.top - b.boundingClientRect.top;
            });

        entering.forEach(function (entry, i) {
            const el = entry.target;
            const delay = Math.min(i, MAX_STAGGER_STEPS) * STAGGER_MS;
            observer.unobserve(el);
            el.style.setProperty('--reveal-delay', delay + 'ms');
            el.classList.add('reveal-in');
            el.classList.remove('reveal-pending');
            setTimeout(function () {
                el.classList.remove('reveal-in');
                el.style.removeProperty('--reveal-delay');
            }, delay + REVEAL_CLEANUP_MS);
        });
    }, { rootMargin: '0px 0px -40px 0px' });

    // Fresh live-search results above the fold settle in quickly instead of snapping
    const SWAP_STAGGER_MS = 30;
    const MAX_SWAP_STEPS = 5;

    function prepare(root, swapped) {
        const viewportBottom = window.innerHeight;
        // Read every position first, then write classes, so layout is computed once
        const cards = Array.prototype.slice.call(root.querySelectorAll('[data-reveal] > *'));
        const tops = cards.map(function (el) { return el.getBoundingClientRect().top; });
        let visibleIndex = 0;
        cards.forEach(function (el, i) {
            if (tops[i] >= viewportBottom) {
                el.classList.add('reveal-pending');
                observer.observe(el);
            } else if (swapped) {
                el.style.setProperty('--reveal-delay', Math.min(visibleIndex++, MAX_SWAP_STEPS) * SWAP_STAGGER_MS + 'ms');
                el.classList.add('swap-in');
                el.addEventListener('animationend', function done(e) {
                    if (e.target !== el) return;
                    el.removeEventListener('animationend', done);
                    el.classList.remove('swap-in');
                    el.style.removeProperty('--reveal-delay');
                });
            }
        });
        settlePhotos(root);
    }

    prepare(document, false);

    // Live search swaps the results grid; prepare the new cards the same way
    document.addEventListener('storefront:results-updated', function (e) {
        prepare(e.target, true);
    });
})();
