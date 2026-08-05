import { tokenize, synonymTokens } from './search.js?v=5';
// ============================================================================
// Question bank — the tested set
// ============================================================================
//
// Every question here has been RUN against the built corpus and kept only if it
// scored at or above 52% confidence AND routed to a specific (non-GENERAL)
// intent. That is the honest way to reach strong demo numbers: choose the
// questions the documentation genuinely answers well, rather than inflating the
// score for questions it does not. Candidates were rejected by that bar,
// including "How is the meter calibrated?" (50.8%) — they stay out until the
// corpus supports them.
//
// Nothing here is cached or pre-written. Asking one of these runs the same
// retrieval, summarisation and confidence path as any typed question, so a
// prospect who goes off-script gets a number computed the identical way and the
// two are directly comparable. That comparability IS the credibility.
//
// The first group is the one to demo from: every question in it is answered by a
// product manual or regulatory filing AND a channel video in the SAME answer.
// That is the cross-source claim made checkable rather than asserted — and it is
// what the "Watch the source" player section below the answer renders from.
//
// Coverage was derived from the corpus rather than guessed: every topic with
// meaningful chunk coverage has at least one question, so a prospect probing an
// area the documentation covers finds it answered.
//
// Measured on the current corpus: 90 questions, 52.0%–87.9%, median 61.0%,
// 87 of 90 drawing on more than one document,
// 24 citing at least one YouTube source,
// 22 citing a document AND a video in the same answer.
// Regenerate by re-running each through buildAnswer() and re-sorting.

export const QUESTION_BANK = [
  // --- Cross-source — documents and video together ---
  "How do I import a plate layout from Data Manager?",                       // 87.87% · doc+video
  "How do I perform a summed volume verification?",                          // 83.26% · doc+video
  "How do I add a library plate model in ArtelWare?",                        // 80.08% · doc+video
  "What is chronic kidney disease screening?",                               // 77.36% · doc+video
  "How do I perform a quality control test on the StatSensor Creatinine meter?", // 76.25% · doc+video
  "What is StatStrip LAC Hb Hct used for?",                                  // 71.24% · doc+video
  "How do I calibrate the Stat Profile Prime Plus?",                         // 65.87% · doc+video
  "What is measured by the Nova Allegro analyzer?",                          // 64.75% · doc+video
  "What is the WOLF G2 cell sorter used for?",                               // 64.56% · doc+video
  "What is the clinical significance of eGFR?",                              // 64.02% · doc+video
  "What is the intended use of the StatSensor Creatinine meter?",            // 63.15% · doc+video
  "How is the StatSensor Creatinine meter used in a clinic?",                // 63.15% · doc+video
  "What is measured in cell culture monitoring?",                            // 62.47% · doc+video
  "What is the intended use of the StatSensor Creatinine analyzer?",         // 60.79% · doc+video
  "What is the hematocrit range for the StatStrip meter?",                   // 60.30% · doc+video
  "How is creatinine measured at the point of care?",                        // 59.64% · doc+video
  "How is hematocrit measured by the StatStrip meter?",                      // 58.06% · doc+video
  "How do I set up the StatStrip Glucose Hospital meter?",                   // 57.92% · doc+video
  "What is the StatStrip Glucose Hospital meter used for?",                  // 57.92% · doc+video
  "How do I perform a multichannel pipette calibration?",                    // 56.27% · doc+video
  "Does oxygen affect the glucose measurement?",                             // 53.61% · doc+video
  "Why measure ionized magnesium instead of total magnesium?",               // 52.00% · doc+video

  // --- Setup, battery and power ---
  "How do I install a new septum?",                                          // 64.17%
  "What is the battery part number for the StatStrip meter?",                // 61.35%
  "How do I install the battery?",                                           // 60.33%
  "What does the low battery indicator mean?",                               // 59.38%
  "How long does the meter battery last?",                                   // 59.37%
  "What is the power up procedure?",                                         // 56.23%

  // --- Calibration and quality control ---
  "How do I manage pipette calibration in ArtelWare?",                       // 64.21% · video
  "How do I perform quality control on the glucose meter?",                  // 61.04%
  "How do I run a quality control test?",                                    // 60.24%
  "How do I run a control test?",                                            // 60.24%
  "What happens if a QC test fails?",                                        // 56.02%
  "How do I run quality control for lactate?",                               // 55.11%

  // --- Cleaning and maintenance ---
  "How do I clean the meter?",                                               // 56.07%
  "How do I clean and disinfect the meter?",                                 // 56.07%

  // --- Test strips, lots and storage ---
  "What is the shelf life of the test strips?",                              // 70.91%
  "What are the storage conditions for glucose test strips?",                // 67.11%
  "How do I store the test strips?",                                         // 64.35%
  "How do I insert a test strip?",                                           // 55.22%

  // --- Samples and specimen handling ---
  "What sample volume does the glucose test need?",                          // 69.30%
  "What is the sample volume required for the lactate test?",                // 69.11%
  "What sample volume does the creatinine test need?",                       // 68.88%
  "What sample volume is required?",                                         // 65.40%

  // --- Interference and hematocrit ---
  "What substances interfere with creatinine measurement?",                  // 61.51%
  "Does hematocrit affect glucose readings?",                                // 56.90%
  "How does hematocrit affect glucose readings?",                            // 56.90%
  "Which drugs interfere with the Allegro UACR assay?",                      // 56.82%
  "What substances interfere with glucose results?",                         // 55.90%
  "What substances interfere with creatinine results?",                      // 55.07%
  "What substances interfere with lactate results?",                         // 54.91%
  "Does acetaminophen affect glucose results?",                              // 54.04%
  "Does maltose interfere with the glucose test?",                           // 53.91%
  "How does hematocrit affect creatinine measurement?",                      // 52.90%

  // --- Operating conditions ---
  "What is the maximum altitude for meter operation?",                       // 72.41%
  "What are the operating temperature and humidity limits?",                 // 64.70%
  "What is the operating temperature range for the analyzer?",               // 64.53%
  "What is the operating temperature range for the meter?",                  // 63.57%
  "What is the operating temperature for the glucose meter?",                // 57.72%
  "How does temperature affect test results?",                               // 54.01%

  // --- Results and ranges ---
  "What are the expected values for creatinine?",                            // 70.48%
  "What is eGFR?",                                                           // 67.12%
  "What is eGFR used for?",                                                  // 67.12%
  "What is the reference range for lactate?",                                // 57.65%
  "What is the measuring range for glucose?",                                // 52.96%

  // --- Intended use and clinical utility ---
  "What is the intended use of the Lactate Plus meter?",                     // 65.13%
  "What is the clinical utility of creatinine measurement?",                 // 59.84%
  "What is the intended use of the Stat Profile Prime Plus?",                // 55.67%
  "What is the clinical significance of measuring lactate?",                 // 52.08%

  // --- Regulatory, clearances and recalls ---
  "What is a predicate device?",                                             // 65.05%
  "What software defects caused a recall?",                                  // 63.83%
  "What was the predicate device for K232075?",                              // 63.08%
  "What is the 510(k) number for the Nova Allegro UACR assay?",              // 62.09%
  "What predicate device was used for the StatStrip Glucose meter?",         // 60.18%

  // --- Analyzers and analytes ---
  "How is hemoglobin measured?",                                             // 58.25%
  "How is blood gas testing performed?",                                     // 56.39%
  "What does the Stat Profile Prime Plus measure?",                          // 55.67%
  "What is ionized magnesium measurement used for?",                         // 53.46%

  // --- Training, software and media ---
  "How do I add an MVS instrument in ArtelWare?",                            // 66.97% · video

  // --- Other product questions ---
  "What are the creatinine control solution levels?",                        // 72.05%
  "What is the precision of the lactate measurement?",                       // 67.51%
  "Why is HbA1c measured in diabetic patients?",                             // 66.60%
  "What methodology does the lactate meter use?",                            // 66.25%
  "How do I run a glucose test?",                                            // 66.16%
  "How does the glucose biosensor work?",                                    // 66.05%
  "What is the measurement range for lactate?",                              // 65.02%
  "What is UACR?",                                                           // 54.69%
  "What is lactate testing used for?",                                       // 53.69%
  "What are the general warnings and precautions?",                          // 53.61%
  "How is lactate measured in the hospital?",                                // 52.70%

];



const STOP = new Set([
  'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'am',
  'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from', 'into', 'onto',
  'and', 'or', 'but', 'if', 'as', 'so', 'than', 'then',
  'this', 'that', 'these', 'those', 'there', 'here',
  'it', 'its', 'do', 'does', 'did', 'done', 'can', 'could', 'would', 'should',
  'who', 'whom', 'what', 'when', 'where', 'why', 'how', 'which', 'whose',
  'i', 'me', 'my', 'you', 'your', 'we', 'our', 'they', 'their',
  'about', 'need', 'needs', 'needed', 'use', 'used', 'using', 'get', 'got',
  'much', 'many', 'any', 'some', 'will', 'shall', 'may', 'might', 'must', 'have', 'has', 'had',
]);

// Light two-phase stemmer (plural, then verb) so singular/plural and simple
// verb forms collide during matching (neonate/neonates, reading/readings,
// strip/strips) without mangling non-plurals (glucose stays glucose).
function stem(t) {
  if (t.length <= 3) return t;
  // plural → singular
  if (t.endsWith('ies') && t.length > 4) t = t.slice(0, -3) + 'y';
  else if (/(ches|shes|xes|zes|sses)$/.test(t)) t = t.slice(0, -2);
  else if (t.endsWith('s') && !t.endsWith('ss')) t = t.slice(0, -1);
  // verb inflection
  if (t.endsWith('ing') && t.length > 5) t = t.slice(0, -3);
  else if (t.endsWith('ed') && t.length > 4) t = t.slice(0, -2);
  return t;
}

// Expand a phrase into a corpus-oriented content-token set: drop stopwords,
// add domain-synonym expansions so "blood" and "sample" collide, and stem so
// plural/verb variants line up.
function contentSet(text, vocab) {
  const toks = tokenize(text).filter(t => !STOP.has(t));
  const set = new Set();
  for (const t of toks) {
    set.add(stem(t));
    if (vocab) for (const s of synonymTokens(t, vocab)) set.add(stem(s));
  }
  return set;
}

// Cosine-style set similarity in [0, 1].
function setSimilarity(a, b) {
  if (a.size === 0 || b.size === 0) return 0;
  let inter = 0;
  for (const t of a) if (b.has(t)) inter++;
  return inter / Math.sqrt(a.size * b.size);
}

// Precompute bank token sets lazily (needs the vocab, available after boot).
let _bankSets = null;
let _bankVocab = null;
function ensureBankSets(vocab) {
  if (_bankSets && _bankVocab === vocab) return;
  _bankVocab = vocab;
  _bankSets = QUESTION_BANK.map(q => contentSet(q, vocab));
}

// Find the closest bank question to `query`. Returns { question, score, index }
// or null. `score` is a 0..1 similarity; the caller decides the threshold.
export function matchQuestionBank(query, opts = {}) {
  const vocab = opts.vocab || null;
  ensureBankSets(vocab);
  const qSet = contentSet(query, vocab);
  if (qSet.size === 0) return null;
  let best = -1, bestScore = 0;
  for (let i = 0; i < _bankSets.length; i++) {
    const s = setSimilarity(qSet, _bankSets[i]);
    if (s > bestScore) { bestScore = s; best = i; }
  }
  if (best < 0) return null;
  return { question: QUESTION_BANK[best], score: bestScore, index: best };
}
