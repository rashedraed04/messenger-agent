/**
 * Hero palms: two gold line-art date palms framing the hero title, drawn here
 * as SVG, no image files. Scrolling is wind: the fronds lift and the crowns
 * lean with scroll speed, then spring back with a little overshoot when the
 * page stops. Each frond is its own composited layer turned by one shared CSS
 * variable per spring, so a frame is a style update plus compositor work.
 * Nothing runs while the page is still or the hero is off screen; visitors
 * who prefer reduced motion get still palms.
 */

(function () {
    const hero = document.querySelector('.hero-section');
    if (!hero) return;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const DESIGN_HEIGHT = 900;  // palm artwork coordinates (420 x 900)
    const CROWN = { x: 230, y: 300 };

    // Deterministic randomness, so both palms look the same on every visit
    function random(seed) {
        return function () {
            seed |= 0;
            seed = seed + 0x6D2B79F5 | 0;
            let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
            t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
            return ((t ^ t >>> 14) >>> 0) / 4294967296;
        };
    }

    const f = (n) => n.toFixed(1);

    // Fronds as [angle in degrees (0 = right, clockwise), length, droop]
    const FRONDS = [
        [-166, 250, 40], [-140, 270, 55], [-113, 225, 38], [-90, 195, 22],
        [-66, 230, 42], [-38, 280, 60], [-12, 295, 72], [14, 262, 82],
        [40, 212, 72], [128, 190, 62], [152, 232, 76], [174, 262, 66],
    ];

    function frondMarkup(id, len, droop, down, rnd) {
        // Local frame: the rachis runs along +x from (0, mid); `down` keeps the
        // droop pointing at the ground whichever way the frond faces
        const leaf = 46;
        const mid = leaf + 6;
        const height = mid * 2 + droop;
        const top = down > 0 ? mid : mid + droop;
        const y = (t) => top + down * droop * t * t;

        let leaflets = '';
        for (let t = 0.1; t <= 1.001; t += 0.034) {
            const px = t * len;
            const py = y(t);
            const along = Math.atan2(2 * down * droop * t, len);
            const size = leaf * (1 - t * 0.72) * (0.85 + rnd() * 0.3);
            const spread = (58 - 26 * t) * Math.PI / 180;
            [-1, 1].forEach(function (side) {
                const a = along + side * spread;
                const ex = px + Math.cos(a) * size;
                // Leaflets sag under their own weight toward the ground
                const ey = py + Math.sin(a) * size + down * size * 0.38;
                const cx = px + Math.cos(a) * size * 0.55;
                const cy = py + Math.sin(a) * size * 0.55;
                leaflets += 'M' + f(px) + ' ' + f(py) + 'Q' + f(cx) + ' ' + f(cy) + ' ' + f(ex) + ' ' + f(ey);
            });
        }
        const rachis = 'M0 ' + f(top) + 'Q' + f(len * 0.5) + ' ' + f(top) + ' ' + f(len) + ' ' + f(y(1));

        return {
            top: top,
            svg: '<svg width="' + Math.ceil(len + leaf) + '" height="' + Math.ceil(height) + '" aria-hidden="true">'
                + '<defs><linearGradient id="' + id + '" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="' + len + '" y2="0">'
                + '<stop offset="0" stop-color="#6b4f12" stop-opacity="0.55"/>'
                + '<stop offset="0.55" stop-color="#c9962a" stop-opacity="0.6"/>'
                + '<stop offset="1" stop-color="#e8c766" stop-opacity="0.45"/>'
                + '</linearGradient></defs>'
                + '<path d="' + leaflets + '" fill="none" stroke="url(#' + id + ')" stroke-width="1.3" stroke-linecap="round"/>'
                + '<path d="' + rachis + '" fill="none" stroke="url(#' + id + ')" stroke-width="2.4" stroke-linecap="round"/>'
                + '</svg>',
        };
    }

    function trunkMarkup(id) {
        // Tapered trunk on a curved centerline from the ground to the crown
        const base = { x: 150, y: DESIGN_HEIGHT + 10 };
        const ctrl = { x: 118, y: 610 };
        const point = (t) => ({
            x: (1 - t) * (1 - t) * base.x + 2 * (1 - t) * t * ctrl.x + t * t * CROWN.x,
            y: (1 - t) * (1 - t) * base.y + 2 * (1 - t) * t * ctrl.y + t * t * CROWN.y,
        });
        const left = [];
        const right = [];
        let rings = '';
        for (let i = 0; i <= 40; i++) {
            const t = i / 40;
            const p = point(t);
            const q = point(Math.min(1, t + 0.01));
            const r = point(Math.max(0, t - 0.01));
            const angle = Math.atan2(q.y - r.y, q.x - r.x) + Math.PI / 2;
            const half = 19 - 9 * t;
            const lx = p.x - Math.cos(angle) * half;
            const ly = p.y - Math.sin(angle) * half;
            const rx = p.x + Math.cos(angle) * half;
            const ry = p.y + Math.sin(angle) * half;
            left.push(f(lx) + ' ' + f(ly));
            right.unshift(f(rx) + ' ' + f(ry));
            // Leaf-scar rings, bowed slightly downward
            if (i % 2 === 1 && t < 0.97) {
                rings += 'M' + f(lx) + ' ' + f(ly) + 'Q' + f(p.x) + ' ' + f(p.y + 5) + ' ' + f(rx) + ' ' + f(ry);
            }
        }
        return '<svg class="palm-trunk" viewBox="0 0 420 ' + DESIGN_HEIGHT + '" aria-hidden="true">'
            + '<defs><linearGradient id="' + id + '" x1="0" y1="0" x2="1" y2="0">'
            + '<stop offset="0" stop-color="#140f06"/><stop offset="0.6" stop-color="#1d1608"/><stop offset="1" stop-color="#3a2b0c"/>'
            + '</linearGradient></defs>'
            + '<path d="M' + left.join('L') + 'L' + right.join('L') + 'Z" fill="url(#' + id + ')" stroke="#aa7c11" stroke-opacity="0.35" stroke-width="1"/>'
            + '<path d="' + rings + '" fill="none" stroke="#d4af37" stroke-opacity="0.3" stroke-width="1"/>'
            + '</svg>';
    }

    // A small hanging cluster of dates under the crown
    function datesMarkup() {
        const rnd = random(7);
        let dates = '';
        for (let i = 0; i < 14; i++) {
            const x = 10 + rnd() * 34 + i * 0.6;
            const y = 8 + i * 3.2 + rnd() * 6;
            dates += '<ellipse cx="' + f(x) + '" cy="' + f(y) + '" rx="3.4" ry="5" fill="#aa7c11" fill-opacity="0.45" stroke="#d4af37" stroke-opacity="0.55" stroke-width="0.8"/>';
        }
        return '<svg class="palm-dates" width="56" height="64" aria-hidden="true">'
            + '<path d="M26 0Q27 20 24 52" stroke="#aa7c11" stroke-opacity="0.6" stroke-width="1.2" fill="none"/>'
            + dates + '</svg>';
    }

    function palmMarkup(side, seed) {
        const rnd = random(seed);
        let fronds = '';
        FRONDS.forEach(function (spec, i) {
            const angle = spec[0] + (rnd() - 0.5) * 6;
            const rad = angle * Math.PI / 180;
            const down = Math.cos(rad) >= 0 ? 1 : -1;
            const frond = frondMarkup('pf-' + side + '-' + i, spec[1], spec[2], down, rnd);
            const flex = 0.75 + rnd() * 0.5;
            // --k: scroll wind lifts the tip (sign follows which way the frond faces);
            // --k2: the whole crown leans, longer fronds more
            const k = (-Math.cos(rad) * flex).toFixed(2);
            const k2 = (flex * spec[1] / 260 * 0.6).toFixed(2);
            fronds += '<div class="frond" style="transform: rotate(' + f(angle) + 'deg)">'
                + '<div class="frond-sway" style="top: ' + f(-frond.top) + 'px; transform-origin: 0 ' + f(frond.top) + 'px; --k: ' + k + '; --k2: ' + k2 + '">'
                + frond.svg + '</div></div>';
        });
        return '<div class="palm palm-' + side + '"><div class="palm-art">'
            + trunkMarkup('pt-' + side)
            + '<div class="palm-crown" style="left: ' + CROWN.x + 'px; top: ' + CROWN.y + 'px">'
            + datesMarkup() + fronds + '</div></div></div>';
    }

    const palms = document.createElement('div');
    palms.className = 'hero-palms';
    palms.setAttribute('aria-hidden', 'true');
    let heroVisible = true;

    function fit() {
        // Size the palms to the hero: crowns about a third of the way down,
        // near the screen edges, trunks running out through the hero's bottom
        const w = hero.clientWidth;
        const h = hero.clientHeight;
        const scale = Math.max(0.3, Math.min(0.75, h / 620, w / 900));
        const crownY = h * 0.32;
        // Phones: the crown sits on the screen edge so the fronds stay clear of the text
        const crownX = w < 576 ? 0 : Math.min(110, w * 0.06);
        palms.style.setProperty('--palm-scale', scale.toFixed(3));
        palms.style.setProperty('--palm-bottom', (h - crownY - (DESIGN_HEIGHT - CROWN.y) * scale).toFixed(1) + 'px');
        palms.style.setProperty('--palm-inset', (crownX - CROWN.x * scale).toFixed(1) + 'px');
    }

    function build() {
        palms.innerHTML = palmMarkup('left', 11) + palmMarkup('right', 23);
        hero.insertBefore(palms, hero.firstChild);
        fit();
        new ResizeObserver(fit).observe(hero);

        // The title gradient (CSS) sleeps while the hero is off screen
        new IntersectionObserver(function (entries) {
            heroVisible = entries[0].isIntersecting;
            hero.classList.toggle('is-paused', !heroVisible);
        }).observe(hero);

        if (!reducedMotion) listen();
    }

    /* ---- Scroll wind: two springs, a quick one (fronds) and a slow one (crown lean) ---- */

    function listen() {
        const quick = { x: 0, v: 0, stiffness: 140, damping: 9 };
        const slow = { x: 0, v: 0, stiffness: 38, damping: 6 };
        let wind = 0;
        let lastY = window.scrollY;
        let lastT = 0;
        let raf = 0;

        function step(spring, target, dt) {
            spring.v += (spring.stiffness * (target - spring.x) - spring.damping * spring.v) * dt;
            spring.x += spring.v * dt;
        }

        function frame(now) {
            const dt = lastT ? Math.min(0.05, (now - lastT) / 1000) : 1 / 60;
            lastT = now;
            const y = window.scrollY;
            const speed = (y - lastY) / dt;  // px per second, positive when scrolling down
            lastY = y;
            const gust = Math.max(-14, Math.min(14, speed * 0.012));
            wind += (gust - wind) * Math.min(1, dt * 10);

            step(quick, wind, dt);
            step(slow, wind * 0.5, dt);
            palms.style.setProperty('--sway', quick.x.toFixed(2));
            palms.style.setProperty('--sway2', slow.x.toFixed(2));

            const settled = Math.abs(wind) < 0.02 && Math.abs(quick.x) < 0.02 && Math.abs(quick.v) < 0.02
                && Math.abs(slow.x) < 0.02 && Math.abs(slow.v) < 0.02;
            if (settled || !heroVisible) {
                raf = 0;
                lastT = 0;
                palms.style.setProperty('--sway', '0');
                palms.style.setProperty('--sway2', '0');
                return;
            }
            raf = requestAnimationFrame(frame);
        }

        window.addEventListener('scroll', function () {
            if (raf) return;
            if (!heroVisible) {
                // Keep the reference fresh so returning to the hero isn't one huge gust
                lastY = window.scrollY;
                return;
            }
            raf = requestAnimationFrame(frame);
        }, { passive: true });
    }

    // Decoration waits for idle, after first paint
    if ('requestIdleCallback' in window) window.requestIdleCallback(build, { timeout: 1500 });
    else setTimeout(build, 400);
})();
