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
   2. Reveal on scroll
   --------------------------------------------------------------------------
   Sections fade and rise a little as they enter. Deliberately restrained: a
   short distance, a single easing, and it runs ONCE per element. Re-animating
   on every scroll direction change is the thing that makes a page feel cheap
   rather than considered.

   prefers-reduced-motion is honoured by not observing at all, so the content is
   simply present - never left hidden by a transition that will not run.
-------------------------------------------------------------------------- */
const REVEAL_SELECTOR = [
  'section > .section-head',
  '.answer-card', '.explain-panel', '.metric-card', '.insight-card',
  '.health-card', '.video-sources', '.graph-value-wrap',
  '.pillars-panel .pillar', '.stat-tile', '.risk-card',
].join(',');

export function initReveal(root = document) {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const targets = [...root.querySelectorAll(REVEAL_SELECTOR)]
    .filter(el => !el.dataset.revealBound);
  if (!targets.length) return;

  if (reduce) {
    targets.forEach(el => { el.dataset.revealBound = '1'; el.classList.add('is-revealed'); });
    return;
  }

  const io = new IntersectionObserver((entries, obs) => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      // Stagger siblings slightly so a row of cards arrives as a sequence
      // rather than a single block appearing at once.
      const sibs = [...(e.target.parentElement?.children || [])];
      const delay = Math.min(sibs.indexOf(e.target), 5) * 55;
      e.target.style.transitionDelay = `${delay}ms`;
      e.target.classList.add('is-revealed');
      obs.unobserve(e.target);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });

  targets.forEach(el => {
    el.dataset.revealBound = '1';
    el.classList.add('will-reveal');
    io.observe(el);
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
