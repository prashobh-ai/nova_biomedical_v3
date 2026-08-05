// ============================================================================
// NLG — turning selected evidence into a reply
// ============================================================================
//
// The summariser decides WHICH sentences answer the question. This module
// decides HOW they are said back to the person who asked.
//
// The difference matters. Before this, an answer was five retrieved sentences
// joined with spaces:
//
//   "AppendixAccuracy Accuracy of the Lactate Plus Meter system was assayed at
//    clinical sites... AppendixMethodology The Lactate measurement is based on
//    the following methodology..."
//
// Everything in it was true and cited. It still reads like a search dump,
// because nothing addresses the person, nothing signals which part is the
// actual answer, and nothing connects one fact to the next.
//
// Three things fix that, none of which require a language model:
//
//   1. CLEANUP    — remove document furniture the reader should never see
//                   (fused headings, section numbers, running labels).
//   2. FRAMING    — open with a sentence that answers in the shape the question
//                   asked for, naming the subject and where the answer came from.
//   3. COHESION   — connect the supporting facts with discourse markers, so the
//                   reader is told how each one relates to the last.
//
// The evidence stays verbatim and stays cited. We are choosing the wrapper and
// the connective tissue, not rewriting the source.

// ---------------------------------------------------------------------------
// 1. Cleanup — document furniture
// ---------------------------------------------------------------------------
const FURNITURE_WORDS =
  'Appendix|Section|Chapter|Contents|Introduction|Overview|Table|Figure|Note|Warning|' +
  'Caution|Methodology|Accuracy|Precision|Specifications?|Limitations?|Panel|Disclaimer|' +
  'Principle|Summary|Purpose|Scope|References?|Indications?|Intended Use|Performance|' +
  'Unit of Measure|Reference Values?|Quality Control|Storage|Calibration';

// A furniture word is only a heading when the REAL sentence starts right after
// it — i.e. the next character is an uppercase letter. Without that guard this
// mangles legitimate sentences: "Accuracy of the Lactate Plus Meter system was
// assayed..." lost its subject and became "Of the Lactate Plus Meter system...".
const LEADING_FURNITURE = new RegExp(
  `^(?:(?:${FURNITURE_WORDS})\\b[\\s:.\\-]*)+(?=[A-Z])`);

// "1-4 ", "A-5 ", "1.4 ", "3.2.1 " at the start of a line
const LEADING_SECTION_NUM = /^(?:[A-Z]?\d+(?:[.\-]\d+)*\s+){1,3}/;

// A document title repeated at the head of its own body text
const LEADING_DOC_ECHO = /^(?:[A-Z][A-Za-z]*\s){0,3}(?:Meter|Analyzer|System|Manual|Guide)\s+(?=[A-Z])/;

// Fused heading + body, e.g. "AppendixMethodology The Lactate...". The pipeline
// splits these at build time, but cleanSentence is the display-layer safety net
// and must not depend on that — an index built before the split still renders
// through here.
const FUSED_FURNITURE = new RegExp(`^(?:${FURNITURE_WORDS})(?=[A-Z])`, '');

export function cleanSentence(text) {
  let t = String(text || '').trim();
  t = t.replace(FUSED_FURNITURE, '');

  for (let i = 0; i < 3; i++) {
    const before = t;
    t = t.replace(LEADING_SECTION_NUM, '');
    t = t.replace(LEADING_FURNITURE, '');
    t = t.replace(LEADING_DOC_ECHO, '');
    if (t === before) break;
  }

  // "Accuracy Accuracy of the..." — heading immediately restated by the body
  t = t.replace(/^(\w+)\s+\1\b/i, '$1');

  // A residual Title Case heading fused to the sentence it introduces:
  // "Intended Use The StatStrip..." / "Unit of Measure Disclaimer The system...".
  // Only stripped when a clear sentence start follows, so ordinary capitalised
  // openings are left alone.
  // Section numbers can sit INSIDE the heading run — "StatSensor Creatinine
  // Meter 1.4 The Sample is..." — so numeric tokens are allowed in the prefix.
  const stripped = t.replace(
    /^(?:(?:[A-Z][A-Za-z]*|[A-Z]?\d+(?:[.\-]\d+)*)(?:\s+(?:of|for|and|the))?\s+){1,6}(?=(?:The|This|These|Each|All|A|An)\s+[A-Za-z])/,
    '');
  // Accept the strip only if what remains is still a usable sentence. Measured
  // in words, not characters: a character floor rejected legitimate short
  // sentences like "The Sample is whole blood."
  if (stripped.trim().split(/\s+/).length >= 5) t = stripped;

  t = t.replace(/\s{2,}/g, ' ')
       .replace(/\s+([,.;:%)])/g, '$1')
       .replace(/\(\s+/g, '(')
       .trim();

  if (!t) return '';
  return t.charAt(0).toUpperCase() + t.slice(1);
}

// ---------------------------------------------------------------------------
// 2. Framing — the opening line
// ---------------------------------------------------------------------------
const CANONICAL = {
  statstrip: 'StatStrip', statsensor: 'StatSensor', xpress2: 'StatStrip Xpress2',
  bioprofile: 'BioProfile', flex2: 'BioProfile FLEX2', allegro: 'Nova Allegro',
  'lactate plus': 'Lactate Plus', 'nova max': 'Nova Max', 'prime plus': 'Stat Profile Prime Plus',
  'nova primary': 'Nova Primary', uacr: 'UACR', egfr: 'eGFR', hba1c: 'HbA1c',
  ph: 'pH', pco2: 'PCO₂', po2: 'PO₂', bun: 'blood urea nitrogen',
};
const GENERIC_FOCUS = new Set(['meter', 'analyzer', 'analyser', 'strip', 'cartridge', 'primary']);

function pretty(term) {
  const key = String(term).toLowerCase();
  if (CANONICAL[key]) return CANONICAL[key];
  return key.replace(/\b\w/g, c => c.toUpperCase());
}

/** A readable subject for the opening line.
 *
 *  Focus terms come out of the question as a flat list — ['statstrip','glucose',
 *  'meter'] — and joining them with "and" produced "StatStrip and Glucose is
 *  described as follows", which reads as two subjects rather than one product.
 *  Product terms and analyte terms compose ("the StatStrip Glucose meter");
 *  two analytes coordinate ("creatinine and hematocrit"). */
function subjectPhrase(analysis) {
  const f = (analysis.focus || []).filter(t => !GENERIC_FOCUS.has(t));
  if (!f.length) return null;

  const products = f.filter(t => CANONICAL[t] && !/^(uacr|egfr|hba1c|ph|pco2|po2|bun)$/.test(t));
  const analytes = f.filter(t => !products.includes(t));

  if (products.length && analytes.length) {
    return `the ${pretty(products[0])} ${analytes.slice(0, 1).map(a => a.toLowerCase()).join('')} system`;
  }
  if (products.length) return `the ${pretty(products[0])}`;
  if (analytes.length >= 2) return `${pretty(analytes[0])} and ${pretty(analytes[1])}`;
  return pretty(analytes[0]);
}

// Openers are phrased as a reply to a person, not as a report header. Each
// intent gets wording that matches the shape of what was asked.
const OPENERS = {
  CLINICAL_SIGNIFICANCE: s => `Here is what the documentation says about why ${s || 'this'} is measured`,
  INTENDED_USE:          s => `${s || 'This product'} is described in the documentation as follows`,
  INTERFERENCE:          s => `On interference affecting ${s || 'these results'}, the documentation states`,
  MECHANISM:             s => `The documentation describes how ${s || 'this'} works as follows`,
  CAUSAL:                s => `On how ${s || 'these factors'} relate, the documentation states`,
  SPECIFICATION:         s => `The documented specifications for ${s || 'this'} are`,
  PROCEDURE:             s => `The documented procedure for ${s || 'this'} is`,
  REGULATORY:            s => `The regulatory record for ${s || 'this'} shows`,
  TEMPORAL:              s => `The record shows the following dates for ${s || 'this'}`,
  COMPARISON:            s => `Comparing them, the documentation states`,
  DEFINITION:            s => `${s || 'This'} is defined in the documentation as`,
  GENERAL:               s => `Here is what the documentation says about ${s || 'this'}`,
};

function buildOpener(analysis, sentences) {
  const subject = subjectPhrase(analysis);
  const fn = OPENERS[analysis.intent.name] || OPENERS.GENERAL;
  const docs = new Set(sentences.map(s => s.chunk.document_id)).size;
  const scope = docs > 1 ? ` — drawn from ${docs} documents` : '';
  const line = `${fn(subject)}${scope}:`;
  return line.charAt(0).toUpperCase() + line.slice(1);
}

// ---------------------------------------------------------------------------
// 3. Cohesion — discourse markers between supporting facts
// ---------------------------------------------------------------------------
//
// The marker is chosen from the RELATIONSHIP between consecutive sentences, not
// picked at random, so it carries real information:
//   * same document, later in it   -> continuation
//   * a different document          -> corroboration
//   * a negation or limitation      -> contrast
const CONTINUE   = ['It adds that', 'The same document notes that', 'It also states that'];
const CORROBORATE = ['Separately,', 'Another source states that', 'Elsewhere in the corpus,'];
const CONTRAST   = ['However,', 'The documentation also cautions that', 'Note, though, that'];
const SPECIFY    = ['Specifically,', 'In more detail,', 'More precisely,'];

const NEGATION_RE = /\b(not|never|no |cannot|must not|should not|excluded|limitation|caution|warning|do not)\b/i;

function pickMarker(prev, curr, usedMarkers) {
  let pool;
  if (NEGATION_RE.test(curr.display) && !NEGATION_RE.test(prev.display)) pool = CONTRAST;
  else if (prev.chunk.document_id !== curr.chunk.document_id) pool = CORROBORATE;
  else if (curr.position > prev.position + 2) pool = SPECIFY;
  else pool = CONTINUE;

  const fresh = pool.filter(m => !usedMarkers.has(m));
  const marker = (fresh.length ? fresh : pool)[0];
  usedMarkers.add(marker);
  return marker;
}

/** Lowercase the first letter when a sentence follows "It adds that ..." so the
 *  join reads as one grammatical sentence rather than two glued together. */
function decapitalise(text) {
  if (PROPER_NOUN_RE.test(text)) return text;
  return text.charAt(0).toLowerCase() + text.slice(1);
}

// Every marker is followed by a lowercase continuation unless the next word is
// a proper noun or acronym. "However, The Lactate Plus meter..." reads as a
// splice; "However, the Lactate Plus meter..." reads as one sentence.
const PROPER_NOUN_RE = /^(?:[A-Z]{2,}|(?:StatStrip|StatSensor|BioProfile|Nova|Lactate|Stat|Allegro|Xpress|FDA|UACR|eGFR|HbA1c|K\d{6})\b)/;

// ---------------------------------------------------------------------------
// 4. Closing — what the answer does not cover
// ---------------------------------------------------------------------------
function buildClosing(analysis, confidence, summary) {
  if (!confidence) return null;

  if (confidence.percent < 30) {
    return `This is a weak match. The corpus does not appear to contain a direct ` +
           `answer, so treat the passages above as related context rather than a settled answer.`;
  }
  if (confidence.signals && confidence.signals.sourceConsensus.value < 0.3) {
    return `All of this comes from a single document. Worth confirming against a second source before relying on it.`;
  }
  if (confidence.signals && confidence.signals.queryCoverage.value < 0.5) {
    return `Part of the question is not covered by the documents found. Narrowing the wording may surface more.`;
  }
  if (summary && summary.rejected > 12) {
    return `Passages that merely repeated the wording of the question were set aside in favour of those that answer it.`;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Main entry
// ---------------------------------------------------------------------------
/**
 * Compose the reply.
 * @returns {{html:string, plain:string, opener:string, closing:string|null}}
 */
// Source marks sit INSIDE the citation superscript, beside the number, because
// that is the moment a reader decides whether to trust a claim: "[2] is a video,
// [3] is the IFU". A mark anywhere else - a panel header, a card title - answers
// the question in the wrong place, after the reader has already moved on.
// Inline SVG so there is no network fetch and no sprite sheet; sized in `em` so
// both marks track the superscript rather than fighting it.
const MARK_YOUTUBE = `<svg class="cite-mark cite-mark-yt" viewBox="0 0 28 20" aria-hidden="true" focusable="false">
  <path d="M27.4 3.1A3.5 3.5 0 0 0 24.9.6C22.7 0 14 0 14 0S5.3 0 3.1.6A3.5 3.5 0 0 0 .6 3.1C0 5.3 0 10 0 10s0 4.7.6 6.9a3.5 3.5 0 0 0 2.5 2.5C5.3 20 14 20 14 20s8.7 0 10.9-.6a3.5 3.5 0 0 0 2.5-2.5c.6-2.2.6-6.9.6-6.9s0-4.7-.6-6.9z" fill="#FF0000"/>
  <path d="M11.2 14.3 18.4 10l-7.2-4.3z" fill="#fff"/>
</svg>`;
const MARK_DOC = `<svg class="cite-mark cite-mark-doc" viewBox="0 0 16 20" aria-hidden="true" focusable="false">
  <path d="M3 0h7l5 5v13a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2z" fill="currentColor" opacity=".28"/>
  <path d="M10 0l5 5h-4a1 1 0 0 1-1-1V0z" fill="currentColor" opacity=".6"/>
  <path d="M4 9h8M4 12h8M4 15h5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" fill="none"/>
</svg>`;

function sourceMark(sourceType) {
  if (sourceType === 'video') return MARK_YOUTUBE;
  return MARK_DOC;          // manuals, IFUs and regulatory records alike
}

export function composeResponse(analysis, sentences, citations, confidence, summary) {
  if (!sentences.length) return { html: '', plain: '', opener: '', closing: null };

  const citeNum = new Map(citations.map(c => [c.chunkIdx, c.num]));
  const citeType = new Map(citations.map(c => [c.chunkIdx, c.chunk && c.chunk.source_type]));
  const opener = buildOpener(analysis, sentences);
  const usedMarkers = new Set();

  const parts = [];
  const plainParts = [];

  sentences.forEach((s, i) => {
    const clean = cleanSentence(s.display);
    if (!clean) return;
    const num = citeNum.get(s.chunkIdx) || 1;

    let body;
    // Steps of a procedure are joined by their own numbering, not by discourse
    // markers. "It adds that remove the back battery cover" is ungrammatical and
    // reads as broken output; the step should simply follow the one before it.
    const isStep = s._proc === true;
    if (i === 0) {
      body = clean;
    } else if (isStep) {
      body = clean;
      plainParts.push(clean);
    } else {
      const marker = pickMarker(sentences[i - 1], s, usedMarkers);
      const joined = decapitalise(clean);
      body = `<span class="answer-marker">${marker}</span> ${joined}`;
      plainParts.push(`${marker} ${joined}`);
    }
    if (i === 0) plainParts.push(clean);

    const srcType = citeType.get(s.chunkIdx);
    const isVideo = srcType === 'video';
    parts.push(
      `<span class="answer-sent">${body}` +
      `<sup class="cite-ref${isVideo ? ' is-video' : ''}" data-cite="${num}" ` +
      `title="Source ${num} — ${isVideo ? 'YouTube video' : 'document'}">` +
      `${sourceMark(srcType)}[${num}]</sup></span>`
    );
  });

  const closing = buildClosing(analysis, confidence, summary);

  const html =
    `<p class="answer-opener">${escapeHtml(opener)}</p>` +
    `<p class="answer-body">${parts.join(' ')}</p>` +
    (closing ? `<p class="answer-closing">${escapeHtml(closing)}</p>` : '');

  return { html, plain: `${opener} ${plainParts.join(' ')}`, opener, closing };
}

/** The "no answer" reply, phrased as a helpful response rather than an error. */
export function composeNoAnswer(analysis, nearestDoc, rejected) {
  const subject = subjectPhrase(analysis);
  const lead = subject
    ? `I could not find a passage in the corpus that answers this about ${escapeHtml(subject)}.`
    : `I could not find a passage in the corpus that answers this.`;

  const detail = rejected > 0
    ? `${rejected} passage${rejected === 1 ? '' : 's'} matched the wording of the question but ` +
      `did not contain ${escapeHtml(analysis.intent.wants || 'an answer')} — so they were set aside rather than ` +
      `presented as an answer.`
    : `Nothing in the indexed documents covers this topic.`;

  const next = nearestDoc
    ? `The closest related document is <strong>${escapeHtml(nearestDoc)}</strong>.`
    : '';

  return `<p class="answer-none">${lead}</p>` +
         `<p class="answer-none-detail">${detail} ${next}</p>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
