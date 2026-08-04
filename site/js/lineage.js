// ============================================================================
// Source Lineage — vertical tree showing how an answer traces back to paragraphs
// ============================================================================

let _onChunkClick = null;

export function initLineage(callbacks = {}) {
  _onChunkClick = callbacks.onChunkClick || (() => {});
}

export function renderLineage(question, answerText, citations) {
  const body = document.getElementById('lineage-body');

  if (!citations || citations.length === 0) {
    body.innerHTML = `
      <div class="lineage-empty">
        <p>No sources retrieved for this question.</p>
      </div>`;
    return;
  }

  // Group citations by document → page → section
  const byDoc = new Map();
  for (const c of citations) {
    const docKey = c.chunk.document_name;
    if (!byDoc.has(docKey)) byDoc.set(docKey, []);
    byDoc.get(docKey).push(c);
  }

  const plainAnswer = answerText.replace(/<[^>]+>/g, '').trim();
  const truncatedAnswer = plainAnswer.length > 240 ? plainAnswer.slice(0, 240) + '…' : plainAnswer;

  const html = `
    <div class="lineage-root">
      <div class="lineage-answer">
        <div class="lineage-eyebrow">Answer</div>
        <div class="lineage-answer-text">${escapeHtml(truncatedAnswer)}</div>
      </div>

      <div class="lineage-tree">
        ${[...byDoc.entries()].map(([docName, cites]) => `
          <div class="lineage-doc">
            <div class="lineage-doc-head">
              <span class="lineage-doc-name">${escapeHtml(stripExt(docName))}</span>
              <span class="lineage-doc-stat">${cites.length} citation${cites.length === 1 ? '' : 's'}</span>
            </div>
            ${cites.map(c => renderPage(c)).join('')}
          </div>
        `).join('')}
      </div>
    </div>`;

  body.innerHTML = html;

  body.querySelectorAll('[data-cid]').forEach(el => {
    el.addEventListener('click', () => {
      _onChunkClick(parseInt(el.dataset.cid, 10));
    });
  });

  const statusEl = document.getElementById('lineage-status');
  if (statusEl) {
    statusEl.textContent =
      `${byDoc.size} document${byDoc.size === 1 ? '' : 's'} · ${citations.length} citation${citations.length === 1 ? '' : 's'} · click any paragraph to inspect`;
  }
}

function renderPage(citation) {
  const c = citation.chunk;
  if (c.source_type === 'video') return renderVideo(citation);
  const sectionPath = c.section_path?.length ? c.section_path.join(' › ') : '(no section)';
  return `
    <div class="lineage-page">
      <div class="lineage-page-info">[${citation.num}] page ${c.page} · ¶${c.paragraph_indices.join(', ¶')}</div>
      <div class="lineage-section">${escapeHtml(sectionPath)}</div>
      <div class="lineage-paragraph" data-cid="${c.id}">
        <div class="lineage-para-num">excerpt</div>
        <div class="lineage-para-text">${escapeHtml(c.paragraph_excerpt || c.text.slice(0, 200))}</div>
      </div>
    </div>`;
}

// A page number is the wrong address for a video. The equivalent is the second
// the sentence was spoken, so the citation embeds the player seeked to that
// second - the reader hears the source say it, which is a stronger check than
// reading a page number.
function renderVideo(citation) {
  const c = citation.chunk;
  const m = c.meta || {};                       // connector metadata lives here
  const vid = m.video_id || '';
  const start = Math.max(0, Math.floor(m.start_sec || 0));
  const stamp = m.timestamp_label || clock(start);
  const transcribed = m.evidence_tier === 'machine_transcribed';
  const watchUrl = c.url || `https://www.youtube.com/watch?v=${vid}${start ? '&t=' + start + 's' : ''}`;
  const embedUrl = `https://www.youtube-nocookie.com/embed/${vid}?start=${start}&rel=0&modestbranding=1`;

  return `
    <div class="lineage-page lineage-video">
      <div class="lineage-page-info">
        [${citation.num}]
        ${transcribed
          ? `<span class="lineage-stamp">spoken at ${escapeHtml(stamp)}</span>`
          : `<span class="lineage-stamp">published video</span>`}
        <span class="lineage-tier ${transcribed ? 'is-transcribed' : 'is-authored'}">
          ${transcribed ? 'auto-transcribed' : 'publisher-written'}
        </span>
      </div>
      <div class="lineage-section">${escapeHtml((c.section_path || []).join(' › '))}</div>
      ${vid ? `
      <div class="lineage-video-frame">
        <iframe src="${embedUrl}" title="${escapeHtml(c.document_name || 'Video source')}"
                loading="lazy" allowfullscreen
                allow="accelerometer; encrypted-media; picture-in-picture"
                referrerpolicy="strict-origin-when-cross-origin"></iframe>
      </div>` : ''}
      <div class="lineage-paragraph" data-cid="${c.id}">
        <div class="lineage-para-num">${transcribed ? 'transcript' : 'description'}</div>
        <div class="lineage-para-text">${escapeHtml(c.paragraph_excerpt || c.text.slice(0, 240))}</div>
      </div>
      <a class="lineage-video-link" href="${watchUrl}" target="_blank" rel="noopener noreferrer">
        Open on YouTube${transcribed ? ' at ' + escapeHtml(stamp) : ''} &rarr;
      </a>
      ${transcribed ? `<div class="lineage-video-note">
        Transcribed automatically. Play from ${escapeHtml(stamp)} to verify against the recording.
      </div>` : ''}
    </div>`;
}

function clock(sec) {
  const s = Math.floor(sec), h = Math.floor(s / 3600),
        m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`
           : `${m}:${String(r).padStart(2, '0')}`;
}

// Helpers
function stripExt(name) {
  return name.replace(/\.[^.]+$/, '').replace(/_/g, ' ');
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}
