# Brag Plan: HVAC-Copilot — "a repair manual that answers back"

> TUTOR BRIEF OVERRIDE: this is a whiteboard explainer LECTURE (not a launch
> video, not 15–25s). `--voice` is ON. Target 4–6+ minutes. Success metric:
> the owner of the repo can explain the system to someone else afterwards.

## What is this app?

HVAC-Copilot turns HVAC service manuals into a grounded question-answerer for
field technicians: exact fault-code lookups rendered verbatim from the manual's
own tables, hybrid retrieval (BM25 + dense + RRF) for everything else, citations
down to the section, and a retrieval-grounded safety refusal that escalates to a
certified technician when no safety-tagged source supports an answer.

## The angle

A patient senior engineer at a whiteboard teaches ONE system to a smart junior
who knows almost nothing about AI. One real scenario carries the whole lecture:
a technician on a rooftop staring at fault code E04, manual in the van,
equipment that can electrocute. No hype adjectives, no launch energy — calm,
precise, friendly. Every technical keyword is defined on screen in one plain
sentence the moment it first appears.

## Hook (first ~45 seconds)

The rooftop: a heat pump flashing E04, a 300-page PDF in the van, forum guesses
on the phone. The tension: "you cannot guess on equipment that can electrocute
you." Then the promise: type the code, get the manual's own row back, quoted.

## Structure (lecture beats, per TUTOR_BRIEF section 7)

1. The real-world problem — rooftop, E04, 300-page manual, electrocution risk.
2. The core idea — RAG as an open-book exam; corpus; parse → chunk → index →
   retrieve → compose.
3. How the pieces work — one whiteboard sketch per concept:
   - chunking (section-aware hierarchy; tables kept whole; metadata)
   - BM25 vs dense retrieval (keyword match vs meaning match) + RRF fusion
   - the fault-code fast path (exact lookup beats AI)
   - citations with receipts + groundedness
   - the safety refusal: why "how much refrigerant" is exempt but "recover the
     refrigerant" escalates; two-tier detection; alarm fatigue
4. The measured numbers and what each means in plain words: recall@5 = 1.0,
   zero safety violations, 38 golden questions, citation precision 0.74,
   groundedness 0.81, zero re-embeds on unchanged corpus, 111 chunks.
5. A 30-second recap the viewer could repeat to a colleague.

## Keywords defined on screen at first use

fault code · RAG · LLM · corpus · chunk / chunking · section-aware hierarchical
chunking · table-as-whole-chunk · metadata · unit model · BM25 · dense
retrieval · embedding · vector · cosine similarity · RRF · hybrid retrieval ·
regex fast path · direct hit · citation · groundedness · safety-critical topic ·
two-tier detection · retrieval-grounded refusal · alarm fatigue · golden set ·
recall@5 · content hash · escalation

## Key moments (the middle)

- The E04 exact row rendering: "Code: E04, Display: ICE, Symptom: Evaporator
  coil iced…" — the manual's row, verbatim, never reworded by the AI.
- The two-librarian whiteboard: BM25's ranked list and the dense list merging
  through RRF into one fused list.
- The safety split-screen: "how much refrigerant does the unit carry?" → spec
  table answer; "recover the refrigerant" → the verbatim escalation message with
  the nearest safety section named.
- The numbers board: recall@5 = 1.0, zero safety violations, 38 golden
  questions.

## Outro / punchline

The recap, then the end card: "A repair manual that answers back — and knows
when not to."

## User flow worth showing

Type "What does fault code E04 mean on the X200?" → exact table row + citation
comes back. Type "recover the refrigerant" → escalation with the nearest safety
section named. These are the two real request/response beats of the product
(recreated as UI cards from the repo's actual outputs).

## Tone

- Preset: polished (mapped from the TUTOR_BRIEF freeform direction)
- Creative direction: whiteboard lecture — patient senior engineer, calm pacing,
  definitions on screen, zero hype.
- Interpretation: long holds, clean crossfades, chalk-on-board visual language,
  sparse quiet SFX, narration sets the pace — never the music.

## Format: landscape — 1920x1080
## Duration: ~5.5–6.5 minutes (TUTOR_BRIEF override of the 15–25s default;
scene durations flex to the generated voiceover audio)

## Visual identity

- Background: deep chalkboard green-slate `#13211d` (subtle paper-grain vignette)
- Text: chalk white `#f2f0e9`
- Accent: amber `#f5b942` (fault codes, hazards) · teal `#63d3c3` (citations,
  answers, safety-ok) · chalk blue `#9ec5e8` (retrieval/diagram strokes)
- Display font: system handwriting-style (e.g. 'Ink Free' with system-ui
  fallback) — chalk feel; body: system-ui
- Strongest visual element: whiteboard diagrams drawn stroke-by-stroke (boxes,
  arrows, ranked lists, the fault row card), keyword definition cards pinned to
  the board corner as each term first appears

## Share copy (draft)

"I built a whiteboard lecture of my own repo: HVAC-Copilot, a repair manual
that answers back — BM25 + dense retrieval fused with RRF, fault-code lookups
that skip the AI, citations with receipts, and a safety refusal grounded in the
index. recall@5 = 1.0, zero safety violations on 38 golden questions."

## Audio direction

- Role: warm, quiet bed under continuous narration (lecture, not ad)
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (steady and
  clean — polished tone), looped back-to-back to cover the full runtime
- Music treatment: volume 0.13 constant (the video is ~100% narration, which
  IS the ducked state per the voiceover rule 0.12–0.15); fade handled by low
  level + final scene
- Music cue guidance: bundled preset exists at
  `assets/music/cues/happy-beats-business-moves-vol-12…music-cues.json`;
  for a narration-paced lecture, natural timing was chosen over beat locks —
  snapping text reveals to beats would fight the voice and reading floors
- Audio-reactive treatment: none — narration-led lecture; music-reactive
  visuals would distract (documented per audio.md)
- SFX posture: very sparse — 3–4 soft cues at scene-major reveals
  (interface/drop on the fault-row card, soft impact on the numbers board)
- Audio-coupled moments: keyword definition cards popping in (soft drop), the
  E04 row card landing (single soft impact), stat numbers counting up
- Restraint rule: audio must never compete with the narration; no dense SFX,
  no beat-grid text reveals

## Voiceover script

Narration is generated per scene with Kokoro (`af_heart`), scene durations flex
to the WAV lengths. Full text in `voiceover-script.txt` (scene-delimited).
~985 words → ~5.5–6.5 minutes at natural pace. Numbers written for TTS
("recall at five of one point zero"), exact figures shown on screen.

## Storyboard

### Scene 1 — The rooftop problem — ~50s
Whiteboard sketch: building silhouette, outdoor unit on the roof, an amber
"E04" chip blinking on the unit, a van with "300-page PDF" in it. Keyword card:
FAULT CODE = "the manufacturer's shorthand for a failure, printed on the
unit's display." Typed question appears in a phone-shaped card. Title card
"HVAC-Copilot — a repair manual that answers back" settles top-left.
Sequential/interaction: the E04 chip blinks (finite), question text types in.
Audio intent: calm scene-setting; one soft drop when the title card lands.
Transition mood: soft crossfade → Scene 2.

### Scene 2 — The core idea: an open-book exam — ~50s
Open-book sketch; the LLM figure at a desk receiving ONLY three page cards
labelled "retrieved chunks". Keyword cards: RAG, LLM, CORPUS. The five-station
pipeline draws left to right: parse → chunk → index → retrieve → compose,
each box popping as named.
Sequential/interaction: pipeline boxes appear one by one (natural, narration-led
timing; not beat-snapped).
Audio intent: steady, building understanding.
Transition mood: soft crossfade → Scene 3.

### Scene 3 — Chunking: cutting the manual without breaking it — ~55s
A manual page sketch cut along heading lines (unit > chapter > section > step)
into chunk cards, one carrying a breadcrumb header `[X200 > Fault Codes > E04…]`.
The fault TABLE block stays whole — highlight ring + "never split" stamp.
Keyword cards: CHUNKING, SECTION-AWARE HIERARCHICAL CHUNKING,
TABLE-AS-WHOLE-CHUNK, METADATA. Counter ticks 15 chapters → 111 chunks.
Sequential/interaction: chunk cards fall out of the page one by one.
Audio intent: methodical, precise.
Transition mood: soft crossfade → Scene 4.

### Scene 4 — Two librarians: BM25 vs meaning, fused — ~65s
Two columns on the board: left "BM25 — keyword librarian" ranked list with E04
on top; right "Dense retrieval — meaning librarian" ranked list. Keyword cards:
BM25, DENSE RETRIEVAL, EMBEDDING, VECTOR, COSINE SIMILARITY, HYBRID RETRIEVAL,
RRF. Arrows from both lists into a fusion node "1/(60 + rank)" producing one
merged list — the fused winner highlighted.
Sequential/interaction: ranked rows appear alternately, then fusion arrows draw.
Audio intent: the "click" of two lists becoming one.
Transition mood: soft crossfade → Scene 5.

### Scene 5 — The fault-code fast path — ~45s
Query card: "What does fault code E04 mean on the X200?" A magnifier regex
scans it, tag "regex fast path"; a big "SKIP SEARCH" stamp; the real manual row
renders verbatim in a card (Code: E04 · Display: ICE · Symptom: Evaporator coil
iced; reduced heating capacity · Likely cause · Corrective action · Severity).
Keyword cards: REGEX FAST PATH, DIRECT HIT.
Sequential/interaction: row fields fill in one by one.
Audio intent: satisfying exactness; one soft impact as the row lands.
Transition mood: clean cut → Scene 6.

### Scene 6 — Citations: answers with receipts — ~40s
Answer card with sentences ending in [C1] [C2]; beneath it, citation chips:
"AriaTherm X200 — Fault Codes > E04" with a teal quote line. Keyword cards:
CITATION, GROUNDEDNESS. A small "every number must exist in the manual" check
with a numeric anchor highlighted.
Sequential/interaction: citation chips slide in after the answer text.
Audio intent: reassurance, verifiability.
Transition mood: soft crossfade → Scene 7.

### Scene 7 — The safety refusal — ~70s
Split screen. Left card (teal): "How much refrigerant does the unit carry?" →
spec-table answer, badge "SPEC LOOKUP — exempt". Right card (amber): "Recover
the refrigerant" → work-verb tag → the verbatim escalation message; badge
"NO SAFETY SOURCE → ESCALATE"; nearest safety section named. Keyword cards:
SAFETY-CRITICAL TOPIC, TWO-TIER DETECTION, RETRIEVAL-GROUNDED REFUSAL, ALARM
FATIGUE.
Sequential/interaction: the two question cards appear one by one; the
escalation message types in.
Audio intent: serious, slower, deliberate — the gravity beat.
Transition mood: soft crossfade → Scene 8.

### Scene 8 — The numbers board — ~50s
Big chalk stats with plain-word captions, appearing one by one:
recall@5 = 1.0 ("the right section was in the top 5, every time") ·
0 safety violations ("the refusal is not accidental") · 38 golden questions
("a fixed exam, written in advance") · citation precision 0.74 ("the honest
weak spot — cross-encoder rerank is the fix") · groundedness 0.81 ·
0 re-embeds on unchanged corpus (CONTENT HASH keyword card).
Sequential/interaction: counters count up to their values.
Audio intent: payoff; one soft impact on the recall number.
Transition mood: soft crossfade → Scene 9.

### Scene 9 — The 30-second recap — ~45s + end hold
Six recap lines appear one by one (chunked meaningful pieces · two-way search
fused · codes are exact lookups · answers cite sections · refusal grounded in
the index · human escalation). Then the end card: "HVAC-Copilot — a repair
manual that answers back. And knows when not to."
Sequential/interaction: recap lines slide in; end card fades up and holds.
Audio intent: warm close; music bed continues then ends with the frame.
Transition mood: fade to end card (final).

**Music mood for this video:** steady, clean, quiet (polished)
**Audio summary:** a quiet corporate-clean bed sits under the entire narration
at 0.13; sparse soft SFX mark only the fault-row reveal, one stat, and the end
card; the voice carries every transition.

## Reading-time floors

Every keyword definition card holds ≥ 0.3s/word after its pop-in; narration
pace (2.4–2.6 w/s) leaves pauses between sentences. No text is pulled before it
can be read; scene lengths are driven by the narration audio itself.
