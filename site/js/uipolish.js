// ============================================================================
// UI polish — playback discipline, motion, and graph controls
// ============================================================================
//
// Three concerns that are presentation-only and therefore kept out of main.js,
// which is already carrying retrieval wiring and answer rendering.

/* --------------------------------------------------------------------------
   1. One video at a time
   --------------------------------------------------------------------------
   Several players can be on screen at once - an answer citing three videos, plus
   the lineage panel. Without discipline, scrolling from one to the next leaves
   the first talking over the second, which sounds broken in a live demo.

   YouTube iframes only accept commands when the embed URL carries
   enablejsapi=1, so the URL is rewritten on the way in. Control is then a
   postMessage; there is no need to load the full IFrame API for pause alone.

   Two rules: a player scrolled substantially out of view pauses, and starting
   one pauses every other. "Starting" is inferred from the click that lands on
   the iframe, since a cross-origin frame gives no play event without the full
   API - a deliberate trade of precision for a much smaller surface.
-------------------------------------------------------------------------- */
const YT_ORIGIN = 'https://www.youtube-nocookie.com';

function ytCommand(iframe, func) {
  try {
    iframe.contentWindow?.postMessage(
      JSON.stringify({ event: 'command', func, args: [] }), YT_ORIGIN);
  } catch { /* frame not ready yet; nothing to pause */ }
}

function enableJsApi(iframe) {
  const src = iframe.getAttribute('src') || '';
  if (!src || src.includes('enablejsapi=1')) return;
  iframe.setAttribute('src', src + (src.includes('?') ? '&' : '?') + 'enablejsapi=1');
}

function allPlayers() {
  return [...document.querySelectorAll('iframe[src*="youtube-nocookie.com/embed"]')];
}

function pauseOthers(active) {
  for (const f of allPlayers()) if (f !== active) ytCommand(f, 'pauseVideo');
}

let visibilityObserver = null;

export function initVideoDiscipline() {
  const players = allPlayers();
  if (!players.length) return;
  players.forEach(enableJsApi);

  if (!visibilityObserver) {
    visibilityObserver = new IntersectionObserver(entries => {
      for (const e of entries) {
        // Below a third visible, the viewer has moved on. Pausing is the polite
        // reading of that, and it is what stops two soundtracks overlapping.
        if (!e.isIntersecting || e.intersectionRatio < 0.35) {
          ytCommand(e.target, 'pauseVideo');
        }
      }
    }, { threshold: [0, 0.35, 0.7] });
  }
  players.forEach(f => visibilityObserver.observe(f));

  // A click landing on an iframe means the viewer pressed play on that one.
  // The window loses focus to the frame, which is the signal we can see.
  if (!window.__ytFocusBound) {
    window.__ytFocusBound = true;
    window.addEventListener('blur', () => {
      const active = document.activeElement;
      if (active && active.tagName === 'IFRAME'
          && (active.getAttribute('src') || '').includes('youtube-nocookie')) {
        pauseOthers(active);
      }
    });
  }
}

/* --------------------------------------------------------------------------
   2. Arrival animations
   --------------------------------------------------------------------------
   Three properties, each of which was wrong in the first attempt:

   CENTRE, NOT EDGE.  A plain IntersectionObserver fires the moment one pixel
   crosses the boundary, so by the time the section is actually being looked at
   the animation has already finished off-screen. The root margin here shrinks
   the trigger zone to the middle band of the viewport, so a section animates
   when it is the thing you are reading.

   BOTH DIRECTIONS.  Scrolling back up a page and finding every section already
   spent is worse than no motion at all. Elements are unset when they leave the
   band and replay on re-entry, which is what makes the readiness gauge redraw
   whether you arrive from above or below.

   NEVER STRANDED.  Everything animated starts at opacity 0, so a trigger that
   never runs would hide content permanently. Anything already past the band on
   load is marked in-view immediately, and reduced-motion skips the observer
   entirely rather than relying on it.
-------------------------------------------------------------------------- */
const INVIEW_SELECTOR = [
  'section', '.section-head', '.answer-card', '.explain-panel',
  '.metric-card', '.insight-card', '.health-card', '.stat-tile', '.risk-card',
  '.heatmap', '.health-rings', '.pillars-panel .pillar',
].join(',');

let inviewObserver = null;

export function initReveal(root = document) {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const targets = [...root.querySelectorAll(INVIEW_SELECTOR)]
    .filter(el => !el.dataset.inviewBound);
  if (!targets.length) return;

  if (reduce) {
    targets.forEach(el => { el.dataset.inviewBound = '1'; el.classList.add('is-inview'); });
    return;
  }

  if (!inviewObserver) {
    inviewObserver = new IntersectionObserver(entries => {
      for (const e of entries) {
        // Replay rather than latch: add on entry, remove on exit.
        e.target.classList.toggle('is-inview', e.isIntersecting);
      }
    }, {
      // Middle band of the viewport: -34% top and bottom leaves roughly the
      // central third as the trigger zone.
      rootMargin: '-34% 0px -34% 0px',
      threshold: 0,
    });
  }

  targets.forEach(el => {
    el.dataset.inviewBound = '1';
    inviewObserver.observe(el);
    // Anything already sitting in or above the band on load must not wait for a
    // scroll that may never come.
    const r = el.getBoundingClientRect();
    if (r.top < window.innerHeight * 0.66) el.classList.add('is-inview');
  });
}

/* --------------------------------------------------------------------------
   3. Graph controls
   --------------------------------------------------------------------------
   The graph is now a panel rather than a background, so it no longer needs a
   mode that lifts it out of one. What it needs is the controls any map has:
   zoom, fit, and a way back to the default view — plus a one-time hint, because
   nothing else on the page signals that the nodes respond to a pointer.
-------------------------------------------------------------------------- */
export function initGraphControls(network, { hostId = 'graph-controls' } = {}) {
  const host = document.getElementById(hostId);
  if (!host || !network) return;

  const scaleBy = factor => {
    const scale = network.getScale() * factor;
    network.moveTo({
      scale: Math.min(4, Math.max(0.08, scale)),
      animation: { duration: 260, easingFunction: 'easeInOutQuad' },
    });
  };

  host.innerHTML = `
    <button class="gctl" data-act="in"  title="Zoom in"  aria-label="Zoom in">+</button>
    <button class="gctl" data-act="out" title="Zoom out" aria-label="Zoom out">&minus;</button>
    <button class="gctl" data-act="fit" title="Fit the whole graph"
            aria-label="Fit the whole graph">&#10530;</button>
    <button class="gctl gctl-wide" data-act="expand" aria-pressed="false"
            title="Expand the map to fill the screen">Expand</button>`;

  host.addEventListener('click', ev => {
    const btn = ev.target.closest('.gctl');
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === 'in') scaleBy(1.35);
    else if (act === 'out') scaleBy(1 / 1.35);
    else if (act === 'fit') {
      network.fit({ animation: { duration: 420, easingFunction: 'easeInOutQuad' } });
    } else if (act === 'expand') {
      // Overlay, never hide. Everything on the page stays where it was; the map
      // simply takes the foreground until Escape or Done. A mode that dimmed the
      // page would only be needed if the graph were still a background.
      const on = document.body.classList.toggle('graph-expanded');
      btn.setAttribute('aria-pressed', String(on));
      btn.textContent = on ? 'Done' : 'Expand';
      // The canvas has resized; vis.js must be told before a fit means anything.
      setTimeout(() => {
        network.redraw();
        network.fit({ animation: { duration: 420, easingFunction: 'easeInOutQuad' } });
      }, 280);
    }
  });

  document.addEventListener('keydown', ev => {
    if (ev.key !== 'Escape' || !document.body.classList.contains('graph-expanded')) return;
    document.body.classList.remove('graph-expanded');
    const btn = host.querySelector('[data-act="expand"]');
    if (btn) { btn.setAttribute('aria-pressed', 'false'); btn.textContent = 'Expand'; }
    setTimeout(() => { network.redraw(); network.fit({ animation: { duration: 380 } }); }, 260);
  });

  // Drop the CSS affordance hint once the canvas has actually been used.
  const canvasHost = document.getElementById('galaxy');
  if (canvasHost) {
    const engage = () => canvasHost.classList.add('is-engaged');
    ['pointerdown', 'wheel'].forEach(e =>
      canvasHost.addEventListener(e, engage, { once: true, passive: true }));
    network.on('hoverNode', engage);
  }

  // The hint has done its job the moment someone hovers a node. Leaving it up
  // after that is clutter over the thing it was pointing at.
  const hint = document.getElementById('graph-hint');
  if (hint) {
    const dismiss = () => {
      hint.classList.add('is-dismissed');
      network.off('hoverNode', dismiss);
    };
    network.on('hoverNode', dismiss);
    setTimeout(dismiss, 12000);          // and it should not linger regardless
  }
}
