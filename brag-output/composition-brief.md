# Hyperframes Composition Brief: HVAC-Copilot — whiteboard explainer lecture

## Objective

Create a long-form whiteboard explainer lecture (NOT a 15–25s launch video —
TUTOR_BRIEF override) teaching HVAC-Copilot to a smart junior. Narration ON
(`--voice`), Kokoro `af_heart`, target ~5.5–6.5 minutes. Calm, precise,
friendly; every keyword defined on screen at first use.

## Output

- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: sum of scene audio lengths + pads (compute from the generated
  voiceover WAVs; do NOT hardcode scene lengths before audio exists)

## Source Material

- Project root: `D:\aria\Projects\HVAC-Copilot`
- Primary files read: README.md, src/hvac_copilot/{service.py, models.py,
  ingest/chunker.py, ingest/indexer.py, retrieve/hybrid.py,
  retrieve/understand.py, qa/compose.py, safety_policy.py, serve/*,
  eval/runner.py, clients/mock.py}, data/qa_golden.jsonl, corpus/*.md
- Product name: HVAC-Copilot
- Tagline: "a repair manual that answers back"
- Key UI/visual moments to recreate: the exact fault-row card, the two-ranked-
  list RRF fusion sketch, the safety split-screen with the verbatim escalation
  message
- Copy that must appear verbatim:
  - "Code: E04 · Display: ICE · Symptom: Evaporator coil iced; reduced heating
    capacity · Likely cause: Low airflow (dirty filter, failed indoor fan) or
    low refrigerant charge · Corrective action: Restore airflow — clean filter,
    verify fan operation · Severity: Moderate" (condense to the card's space —
    the point is "the manual's row, verbatim")
  - "I can't give procedural guidance for this. The question involves
    refrigerant for the X200, which is safety-critical, and no section tagged
    as safety documentation supports an answer here. Stop and contact a
    certified HVAC technician; a supervisor has been flagged to review this
    request."
  - Question cards: "How much refrigerant does the unit carry?" (exempt) vs
    "Recover the refrigerant" (escalates)
  - Numbers: recall@5 = 1.0 · 0 safety violations · 38 golden questions ·
    citation precision 0.74 · groundedness 0.81 · 111 chunks · 15 chapters

## Creative Direction

- Tone preset: polished
- Creative direction: whiteboard lecture — patient senior engineer teaching one
  system; chalk-on-board aesthetic; zero hype; definitions pinned as cards
- Angle: rooftop technician + E04 scenario carries the whole lecture
- Hook: the rooftop, the blinking E04, the 300-page PDF in the van
- Outro / punchline: "A repair manual that answers back. And knows when not to."
- Avoid:
  - Generic SaaS language, launch energy, hype adjectives
  - Abstract filler visuals (every sketch is a concept from the repo)
  - Beat-grid text reveals that outrun the narration

## Visual Identity

- Background: `#13211d` chalkboard green-slate, subtle vignette
- Text: chalk white `#f2f0e9` (body ≥ 28px at 1080p)
- Accent: amber `#f5b942` (fault/hazard), teal `#63d3c3` (answers/citations),
  chalk blue `#9ec5e8` (diagram strokes)
- Display font: 'Ink Free', system-ui fallback (chalk handwriting feel); body
  font: system-ui, sans-serif
- Visual references from the project: fault table row structure, breadcrumb
  format `[AriaTherm X200 > Fault Codes > E04 …]`, pipeline stations
  parse → chunk → index → retrieve → compose

## Storyboard

Use `brag-plan.md` as the creative contract. Nine scenes:

1. The rooftop problem — ~50s — E04 blinking, van + PDF, typed question, title
2. Open-book exam — ~50s — RAG/LLM/corpus cards, 5-station pipeline
3. Chunking — ~55s — heading-tree cuts, table-kept-whole stamp, 111 counter
4. Two librarians — ~65s — BM25 list vs dense list → RRF fused list
5. Fault-code fast path — ~45s — regex scan, SKIP SEARCH, verbatim row card
6. Citations — ~40s — [C1][C2] answer card, citation chips, number anchoring
7. Safety refusal — ~70s — exempt vs escalate split screen, verbatim refusal
8. Numbers board — ~50s — six stats count up with plain-word captions
9. Recap + end card — ~45s+ — six recap lines, closing card holds

Keyword definition cards: pinned top-right of the board as each term first
appears; term + one plain sentence; hold ≥ 0.3s/word.

## Audio

- Audio role: warm quiet bed under continuous narration
- Audio arc: bed starts low, stays low (narration is ~100% of runtime), ends
  with the final frame
- Music: `assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3`
  (copy from skill assets); loop back-to-back (two elements at data-start 0 and
  data-start <source-length>) to cover full runtime; volume 0.13
- Music cue guidance: preset JSON exists in the skill's music/cues/ directory;
  natural timing chosen over beat locks — narration-paced lecture, cues would
  fight reading floors
- Audio-reactive treatment: none (narration-led lecture — documented decision)
- Audio-coupled moments:
  - keyword definition cards — soft drop pop-in
  - fault-row card landing — single soft impact
  - stats count-up on the numbers board — subtle ticks allowed, no dense SFX
- SFX selection guidance: prefer low high-frequency-risk files
  (interface/drop_001, impact/impactSoft_medium_*); ≤ 5 SFX total; volume
  0.4–0.6, quieter than the bed
- Exact SFX choice: Hyperframes chooses filenames/timestamps after animation
  exists; copy chosen files into `composition/assets/sfx/`
- Voiceover: per-scene WAVs generated via `npx hyperframes tts --voice
  af_heart` into `composition/assets/voiceover/voice_01.wav … voice_09.wav`;
  each wired on its own track (`data-track-index` 3..11, data-volume 1);
  scene `data-start`/`data-duration` derive from measured WAV durations
  (0.35s lead-in, ~0.35s tail per scene; +1.2s title settle on scene 1; +2.5s
  end hold on scene 9). Root `data-duration` = total.

## Hyperframes Instructions

Load `hyperframes-core`, `hyperframes-animation`, `hyperframes-creative`,
`hyperframes-keyframes`, `hyperframes-cli`. /brag owns the angle; Hyperframes
owns composition structure, exact timing, lint, render.

Requirements:
- Single standalone `index.html`, one paused GSAP timeline registered at
  `window.__timelines["hvac-lecture"]` matching the root `data-composition-id`.
- Never tween `.clip` elements (animate inner wrappers); no CSS-transform +
  GSAP conflicts; every `<audio>` has an id; no `crossorigin`; no network at
  render time (GSAP via CDN is standard in skeletons — prefer a local copy if
  check flags failed requests).
- Scenes are contiguous `.clip` sections; entrance fades on inner wrappers;
  chalk-stroke diagram accents may draw in (opacity/scale, no heavy motion).
- All text ≥ 28px, chalk-on-dark contrast ≥ WCAG (light chalk on #13221d is
  high contrast; amber on dark passes for large text only — keep amber text
  ≥ 32px bold or use it for borders/underlines).
- Deterministic: no Math.random, no Date.now, finite repeats only.
- Run `npx hyperframes check` before render — the single gate; fix every error
  including WCAG contrast findings.
- Render with `--quality delivery` (long-form lecture, final delivery).
