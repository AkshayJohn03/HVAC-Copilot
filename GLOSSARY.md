# HVAC-Copilot Glossary — every keyword in this repo, in plain English

This is the study companion to the repo (and to the explainer video). Every
technical term the code uses is defined below in one to three plain sentences,
grouped by theme, each with a note on **why it matters here**. Read it front to
back and the module map in the README will read like prose.

---

## 1. RAG & Documents — turning a 300-page manual into answerable pieces

**LLM (Large Language Model)**
The text-generation engine: a model that reads a prompt and writes an answer.
This is what happens when the assistant forms the sentences of a reply — in
this repo it is a swappable client that can be a real provider or an offline
mock.
*Why it matters here:* the LLM only ever writes the wording of answers; it is
never allowed to invent facts — the manual excerpts it sees are the whole menu.

**RAG (Retrieval-Augmented Generation)**
The pattern of first *retrieving* the relevant pages from your own documents,
then *generating* an answer from only those pages. Think "open-book exam":
the model must quote the book it was handed, not recite from memory.
*Why it matters here:* RAG is the whole architecture — parse → chunk → index →
retrieve → compose — and it is what makes an answer about "E04" come from the
actual manual instead of a forum guess.

**Corpus**
The full collection of documents a system can answer from, as a set of files.
Here it is the `corpus/` folder: 15 markdown chapters for two fictional units
(AriaTherm X200, VeyraCool V9), committed so tests run offline.
*Why it matters here:* everything the copilot can say lives in the corpus; if
it is not in the corpus, the system refuses or says what is missing.

**Manual / manual chapter**
The real-world source document — a service manual split into numbered chapters
(Overview, Fault Codes, Wiring, Refrigerant Safety, …). Each `.md` file in the
corpus is one chapter of one unit's manual.
*Why it matters here:* manuals have structure (tables, step procedures, danger
notices), and the whole pipeline is built to preserve that structure rather
than shred it.

**Document parser (`ingest/parser.py`)**
The first pipeline stage: reads a markdown file (or PDF) and works out its
structure — headings, sections, tables with their rows, DANGER/WARNING blocks,
image references.
*Why it matters here:* retrieval quality is decided here; a table row parsed
wrong is a fault code that can never be looked up exactly.

**Chunk / chunking**
A chunk is one piece of the manual small enough to retrieve as a unit; chunking
is the act of cutting the document into those pieces. Cut too coarsely and you
retrieve a whole chapter when you needed one row; cut too finely and you
retrieve a sentence with no context.
*Why it matters here:* the copilot indexes 111 chunks from the 15-chapter
corpus — those chunks are the only things search and citations can point at.

**Section-aware hierarchical chunking (`ingest/chunker.py`)**
Instead of slicing every 500 characters blindly, the chunker walks the manual's
heading tree (unit → chapter → section → step) and cuts at meaningful
boundaries, prefixing each chunk with its "breadcrumb" path.
*Why it matters here:* a repair procedure never gets sliced mid-step, and every
chunk knows exactly where in the manual it lives — which is what makes
citations possible.

**Table-as-whole-chunk**
A rule of the chunker: a table (like the E01–E88 fault-code table) is never
split across chunks — it is kept whole with its caption and header row.
*Why it matters here:* a fault table row split from its header becomes
unretrievable nonsense ("High discharge temperature" with no code attached);
keeping tables whole is what makes exact-code lookup work.

**Step-group chunks**
Numbered procedures are grouped into chunks of steps (four at a time), never
split in the middle of one step.
*Why it matters here:* answers that skip "the step where the danger lives" are
the failure mode this exists to prevent.

**Breadcrumb header**
The `[AriaTherm X200 > Fault Codes > E04 Evaporator coil frost]` prefix written
into the text of every chunk.
*Why it matters here:* the breadcrumb is inside the text, so both keyword
search and vector search can match on "which chapter is this from", not just
the body words.

**Chunk overlap**
When an over-long section must be split, the split carries the last paragraph
forward into the next piece so no idea is severed at the boundary.
*Why it matters here:* a rule that straddles a split is still findable from
either side.

**Metadata**
The labelled facts attached to every chunk beyond its text: which source file,
which unit model, whether it is safety-tagged, which fault codes it anchors.
*Why it matters here:* filters like "only the V9 chiller's manual" are answered
from metadata in one pass, before any text scoring happens.

**Unit model**
Which machine the question is about — `X200` heat pump or `V9` chiller.
*Why it matters here:* the X200's E-codes and the V9's E-codes are different
tables; the detected unit locks a metadata filter so answers never mix manuals.

**Fault code**
The manufacturer's shorthand for a failure (E04, E28, …) printed on the
unit's display. In this repo each code anchors to the exact table row that
lists symptom, likely cause, corrective action, and severity.
*Why it matters here:* fault codes are exact strings, not paraphrases — which
is precisely why the retrieval system has an exact-lookup path.

**Fault-code registry / row registry (`DirectHit`, `row_registry`)**
A dictionary built at index time: code → the chunk holding that row, plus the
row's column values. Looking up "E04" is a dictionary hit, not a search.
*Why it matters here:* this registry is the machinery behind "type the code,
get the row" — deterministic and verbatim.

**VLM (Vision-Language Model)**
An AI model that looks at an image and describes it. The `qa/multimodal.py`
path sends a nameplate photo to a VLM, reads the model number, and aims
retrieval at that unit's manual.
*Why it matters here:* techs photograph nameplates, not type serial numbers;
offline a deterministic mock stands in so the flow is testable without a
deployed vision model.

**Deterministic corpus generator (`scripts/build_corpus.py`)**
A Python script that writes the entire synthetic corpus, byte-for-byte
identical on every run (tested).
*Why it matters here:* it makes the whole suite reproducible — same corpus,
same index, same scores, every time, on any machine.

---

## 2. Retrieval — finding the right page for a technician's fragment

**Query understanding (`retrieve/understand.py`)**
The stage that turns a typed fragment ("v9 keeps tripping", "what's E04") into
a structured plan: detected unit, extracted fault codes, expanded slang, safety
topics, intent.
*Why it matters here:* technicians type like they talk; this stage is the
translator between field language and manual language.

**Slang normalization**
A lookup table mapping field phrasing to manual vocabulary: "icing up" expands
to "coil frost, defrost, evaporator"; "tripping" to "breaker, overcurrent".
Expansions are appended to the search query, never shown to the user.
*Why it matters here:* the manual never says "it's tripping" — without
normalization, a symptom described in slang would retrieve nothing.

**Regex fast path (fault-code direct hit)**
Before any search runs, a regular expression pulls code candidates ("E04") out
of the question and validates them against the fault-code registry. A validated
code *is* the answer — retrieval is skipped entirely.
*Why it matters here:* a code lookup should be a lookup, not a similarity
contest; the fast path removes latency and failure modes from the most common
question type.

**BM25**
A classic keyword-ranking formula: score documents by how often your search
terms appear in them, weighted by how rare those terms are across the whole
corpus, with a dampener for long documents. It matches *words*, not *meanings*.
*Why it matters here:* "E04", part numbers and torque values are exact strings
— BM25 is the precision backbone for exactly those.

**Okapi IDF (inverse document frequency)**
The weighting inside BM25: a term that appears in 3 of 111 chunks is worth far
more than one that appears in 90. This repo hand-rolls the smoothed Robertson–
Sparck-Jones variant so scores are always positive.
*Why it matters here:* it is what makes "refrigerant" a strong clue and "the"
worthless, computed from the corpus itself.

**Tokenization / stop words**
Splitting text into lowercase word tokens and dropping the glue words ("the",
"is", "what") that carry no meaning. Codes like "e04" survive filtering.
*Why it matters here:* BM25 and the local embedder both tokenize, and
deliberately letting short code-like tokens survive is a small decision with
big retrieval consequences.

**Dense retrieval**
Matching by *meaning* instead of exact words: text is mapped to points in
vector space and nearby points are semantically related, so "not cooling" can
land near "low cooling capacity".
*Why it matters here:* slang and typos have near-zero BM25 overlap with the
manual's wording — the dense channel is what catches them.

**Embedding**
The act of converting a piece of text into a list of numbers (a vector) that
represents its meaning.
*Why it matters here:* every one of the 111 chunks is embedded at index time,
and the question is embedded at query time so the two can be compared.

**EmbeddingClient (protocol)**
The interface every embedding provider must satisfy — a `dim` and an
`embed(texts)` method. The pipeline depends on this protocol, never on a
concrete SDK.
*Why it matters here:* swapping a dev-grade embedder for a real one is one
environment variable, no code changes.

**Hashed / local embedding (`LocalHashEmbedding`)**
The offline default embedder: character n-grams of each word are hashed into a
fixed-size vector with TF-IDF weighting learned from the corpus. Deterministic,
dependency-free, documented as dev-grade — it is strong on typos and
inflections, not a trained semantic encoder.
*Why it matters here:* it lets the entire suite run offline with honest,
reproducible numbers, while the protocol keeps the door open for real
embeddings.

**Hashing trick**
Mapping features into a fixed-size vector by hashing them, so no vocabulary
table needs to be stored in memory.
*Why it matters here:* it is how the local embedder stays tiny and
deterministic across platforms.

**TF-IDF**
Term Frequency × Inverse Document Frequency: weight a word by how often it
appears in *this* text, discounted by how common it is *everywhere*. The local
embedder fits an IDF table from the corpus.
*Why it matters here:* rare n-grams ("e23") dominate the vector's direction
while boilerplate ("ing") vanishes — that is what makes cosine discriminative.

**Vector**
The list of numbers an embedding produces — a point in high-dimensional space.
*Why it matters here:* the index is one big matrix of chunk vectors (N × dim),
row-aligned with the chunks themselves.

**Cosine similarity**
The similarity of two vectors measured as the cosine of the angle between
them: 1.0 = same direction, 0.0 = unrelated. Length is ignored.
*Why it matters here:* dense retrieval scores every chunk this way, and the
semantic query cache uses the same measure to spot "I've basically answered
this before".

**Hybrid retrieval (`retrieve/hybrid.py`)**
Running keyword (BM25) and meaning (dense) search in parallel and merging the
two ranked lists.
*Why it matters here:* fault codes are exact-lexical — dense-only collapses;
symptom slang is paraphrase — BM25-only collapses; neither alone survives a
technician's real questions.

**RRF (Reciprocal Rank Fusion)**
The merging method: each document scores a point for every list it appears in,
weighted by `1/(k + rank)` with k=60 — being 1st or 3rd in both lists beats
being 1st in one and missing in the other. It fuses lists without ever trying
to compare BM25 and cosine scores directly (they live on incomparable scales).
*Why it matters here:* RRF optimizes recall robustness, not top-1 precision —
the repo documents the "RRF dilution" caveat it paid for and ships the
reranker as the repair.

**Top-k**
How many retrieved pieces you keep — the best k chunks after scoring. Default
here is 5, hard-capped at 50 by the API.
*Why it matters here:* top-k is the dial that trades answer richness against
noise and prompt size; recall@k is measured against it.

**Candidate pool**
The larger shortlist (50 here) fusion and the reranker work over before the
final top-k is cut.
*Why it matters here:* reranking is only useful if the right chunk survived
into the pool — recall first, precision second.

**Reranker**
A second-pass scorer that re-orders the fused candidate pool. The offline
default is a candidate-local BM25; a cross-encoder can be configured.
*Why it matters here:* it repairs RRF's top-1 precision — the measured lesson
from the author's RAG_showcase, reproduced and tested here.

**Cross-encoder**
A reranker model that reads the question and a candidate chunk *together* and
scores how well the pair matches — more accurate than comparing them
separately, but too slow to run over the whole corpus (hence pool-only).
*Why it matters here:* the interface is already flagged in `build_reranker`;
it is the roadmap fix for citation precision.

**MMR (Maximal Marginal Relevance)**
A selection rule that balances relevance against redundancy: after picking a
strong chunk, prefer the next one that is relevant *and different* from what
is already picked.
*Why it matters here:* it stops the top-5 from being five near-identical
paragraphs of the same overview section.

**Metadata filter (`Filters`)**
The numpy mask applied before scoring: restrict to a unit model, a document
type, or safety-tagged chunks only.
*Why it matters here:* "answers about the V9 only" is enforced structurally,
not hoped for from the ranking.

**Incremental indexing (`ingest/indexer.py`)**
On re-ingest, chunks whose content is unchanged skip the embedder entirely;
only new or updated chunks are embedded. The stats report new / updated /
unchanged so the behavior is observable.
*Why it matters here:* re-embedding an unchanged 300-page manual is the
classic RAG cost bug — a tech syncing a manual revision should not re-pay for
14 unchanged chapters (and the test proves zero re-embeds).

**Content hash**
A whitespace-insensitive SHA-256 of a chunk's text, computed once and stored
on the chunk. Same hash → same content → reuse the old vector.
*Why it matters here:* it is the cheap fingerprint that makes incremental
indexing trustworthy across re-wraps of the same paragraph.

**Snapshot store (`JsonSnapshotStore`)**
The whole index — chunk metadata plus vectors — persisted as one portable
JSON file, written via a temp file and an atomic replace so a crash mid-write
cannot corrupt the old snapshot.
*Why it matters here:* field/offline mode is "copy one file to the device";
queries then need no network at all.

**WAL (write-ahead log) / atomic write**
A WAL is the database technique of recording changes to a durable journal
*before* applying them, so an interrupted operation resumes or rolls back
cleanly. This repo uses the sibling pattern where a full WAL is overkill: the
snapshot is written to `index_snapshot.tmp` and then atomically replaced, so
readers only ever see a complete old index or a complete new one.
*Why it matters here:* it is what makes "sync one JSON file to the van
laptop" crash-safe without database infrastructure.

**Qdrant (snapshot store)**
An open-source vector database offered as an optional persistence backend
(`pip install 'hvac-copilot[qdrant]'`); the JSON mirror stays diffable.
*Why it matters here:* when the index outgrows a single file, the vector store
takes over persistence behind the same interface.

**Two-tier query cache (exact + semantic)**
Repeated questions short-circuit retrieval and composition: first an exact
match on the normalized question, then a semantic match where the new
question's vector sits within cosine 0.93 of a cached one.
*Why it matters here:* "what's E04" and "what does E04 mean" are the same
question to a technician — the cache makes the second one nearly free, and the
cache is invalidated whenever the index changes.

**LRU / TTL**
Least-Recently-Used (evict the oldest-touched entry when full) and
Time-To-Live (expire entries after an age). The idempotency store is LRU-512
with a 1-hour TTL.
*Why it matters here:* bounded memory and stale-entry protection are what let
caches live safely inside a long-running server.

---

## 3. Answering & Safety — receipts, refusals, and no alarm fatigue

**Grounding / grounded answer**
An answer assembled only from retrieved manual chunks, with the system prompt
forbidding invention and requiring exact quotes for numbers.
*Why it matters here:* grounding is the difference between "the manual says"
and "the model thinks" — on a rooftop, only the first is acceptable.

**Citation (with receipts)**
Every answer names the document, section path, and breadcrumb of each chunk it
used — derived from what the answer actually used (explicit [C1] markers, then
lexical overlap), not from what the model *claims* it used.
*Why it matters here:* a technician can verify the answer against the manual,
and citation precision can be *measured* rather than trusted.

**Citation precision**
Of the citations returned, the fraction that land on the section the golden
set says was expected. Measured 0.74 here — the overview section occasionally
outranks the specific one; cross-encoder rerank is the roadmap fix.
*Why it matters here:* it is the honest number: the repo reports it rather
than rounding the story.

**Groundedness**
How much of the answer's content is actually backed by retrieved context —
here a deterministic heuristic: lexical coverage (weight 0.6), every number in
the answer must exist in the context (weight 0.4), minus a penalty for
unsupported "not/never" sentences.
*Why it matters here:* it catches the classic failure — fluent sentences with
invented numbers — cheaply and repeatably, with no judge model in the loop.

**Faithfulness**
The general quality of the answer saying only what its sources support (no
paraphrase drift, no invented facts). Groundedness is this repo's measurable
proxy for it.
*Why it matters here:* for fault tables the composer skips the model entirely
and renders the row verbatim — faithfulness 100% by construction.

**Extractive answer (offline mock LLM)**
The bundled mock LLM answers strictly by quoting sentences from the context
blocks it was handed — it cannot invent.
*Why it matters here:* it makes groundedness and citation metrics measure the
real retrieval pipeline, not an echo chamber, with zero network.

**Safety-critical topic**
A category of question where wrong guidance can hurt someone: refrigerant
handling, pressurized systems, energized electrical work, gas/combustion.
Centralized in `safety_policy.py` so retrieval, QA and eval all agree.
*Why it matters here:* equipment that can electrocute or vent refrigerant
deserves a harder edge than "please be careful".

**Two-tier topic detection**
Tier 1: phrases that *describe* hazardous work ("recover", "pressure test",
"live circuit") always count. Tier 2: a refrigerant designation ("R32") counts
only when combined with a work verb.
*Why it matters here:* "refrigerant circuit" appears in maintenance schedules;
treating every mention as hazardous would fire the guardrail on benign
questions all day.

**Escalation / guardrail**
When a question is safety-critical and *no* retrieved chunk carries the
safety tag, the composer refuses procedural guidance, names the topic
categories, cites the nearest indexed safety section, and flags a supervisor —
the LLM is never even called.
*Why it matters here:* the refusal is computed from retrieval state, so it is
deterministic, unit-testable, and auditable.

**Retrieval-grounded refusal**
A refusal justified by an auditable fact — "no safety-tagged source supports
this" — rather than a model's unverifiable opinion that it "shouldn't answer".
*Why it matters here:* a model asked to be careful can be talked into
procedure-by-procedure leakage; a refusal computed from the index cannot.

**False-positive alarm fatigue**
The erosion of trust when a guardrail fires on harmless questions — users
learn to ignore it, and then it fails exactly when it matters.
*Why it matters here:* it is the design force behind both exemptions: "how
much refrigerant does the unit carry?" is a spec lookup and must *not*
escalate, while "recover the refrigerant" — same noun, work verb — must.

**Spec-lookup exemption**
The deliberate rule (regex) that quantity questions about a designation
("how much R32 charge…") never escalate, because naming a factory charge
weight synthesizes nothing.
*Why it matters here:* a guardrail that nags about spec lookups trains users
to dismiss it; the exemption is what keeps escalations credible.

**Per-stage trace timings**
Every answer carries `trace.timings_ms` — understand / retrieve / compose /
total — plus the retrieval branch scores.
*Why it matters here:* "why was that slow?" is answered with data, and the
ForensiQ-compatible traces make the whole portfolio debuggable.

---

## 4. Serving — the API a field app actually talks to

**FastAPI**
The Python web framework serving the API (`serve/app.py`): typed request
models, automatic validation, and routes for `/v1/query`, `/v1/query/stream`,
`/v1/ingest`, `/v1/health`, `/v1/metrics`.
*Why it matters here:* it turns the in-process `HVACCopilot` facade into a
deployable service without changing the pipeline.

**ASGI**
The Python standard that lets async web servers and applications talk. Pure-
ASGI middleware here means request/response wrappers written directly against
that standard — no buffering, so SSE streams flow untouched.
*Why it matters here:* the whole serving stack (auth, limits, idempotency,
correlation ids) is a stack of small auditable wrappers, and tests drive the
app through httpx's ASGI transport — no sockets opened.

**Middleware**
Code that wraps every request on its way in and every response on the way
out. The chain here: correlation id → deprecation stamp → auth → body-size
limit → idempotency → route.
*Why it matters here:* cross-cutting concerns live in one reviewed place
instead of being copy-pasted into every handler.

**SSE (Server-Sent Events)**
A streaming HTTP format where the server pushes `event:`/`data:` lines as the
answer is generated — `/v1/query/stream` emits meta → token* → done.
*Why it matters here:* a technician sees words appear as they are generated
instead of staring at a spinner, and the guardrail still runs before the
first token.

**Prometheus metrics**
The standard text format (`/v1/metrics`) monitoring systems scrape: counters
like `hvac_queries_total`, `hvac_cache_hits_total`,
`hvac_guardrail_escalations_total`, plus per-stage latency summaries.
*Why it matters here:* a dependency-free registry means production observability
ships in the box — including a counter for every safety escalation.

**p50 / p95 / p99 (percentiles)**
Latency checkpoints: p50 is the median request (half finish faster), p95 is
the point where 95% finish faster, p99 the 99% mark. Averages hide the
unlucky tail; percentiles don't.
*Why it matters here:* the eval reports latency p50/p95 and the metrics
registry renders the same quantiles — slowness is measured, not felt.

**Correlation ID**
An identifier (`X-Correlation-ID` or a generated uuid4) attached to a request,
echoed on the response, and written into the answer's trace — so every log
line about one question can be joined across the stack.
*Why it matters here:* "the tech said it failed at 14:32" becomes findable
with one string instead of archaeology.

**Idempotency key**
An optional `Idempotency-Key` header on `POST /query`: the response is cached
under `sha256(key + body)`, and a retry with the same key replays the stored
JSON (flagged `X-Idempotent-Replay: true`) instead of re-running the pipeline
— concurrent duplicates serialize per key.
*Why it matters here:* flaky van Wi-Fi means retries are normal; the retry
gets the same answer without double work.

**API-key auth**
When `HVAC_API_KEYS` is set, `/query*` and `/ingest` require `X-API-Key` and
fail with a generic 401 otherwise; `/health` and `/metrics` stay open.
Unset → auth disabled with a startup warning, so existing deployments keep
working.
*Why it matters here:* it is the minimum viable gate for exposing the service
beyond localhost.

**SHA-256 at rest**
API keys are hashed at ingest; only the SHA-256 hashes are stored, compared in
constant time, and raw keys are never logged or echoed.
*Why it matters here:* a leaked config dump or log file cannot leak usable
keys.

**`/v1` versioning**
Canonical routes live under `/v1/...` so future breaking changes can ship as
`/v2` without breaking existing clients.
*Why it matters here:* the API contract is now explicit — field apps update
on their own schedule.

**Deprecation / Sunset headers**
Every response on the legacy unversioned paths carries `Deprecation: true` and
a `Sunset` date (RFC 8594) for one release of grace.
*Why it matters here:* old clients are told — in the protocol, not a changelog
— exactly how long they have to migrate.

**Request limits (413 / 422)**
Question bodies over 8 KiB are rejected with 413 and `top_k` above 50 with
422, before the pipeline is ever invoked.
*Why it matters here:* a hostile or buggy client cannot cost you an embedding
call or a giant prompt.

**Offline mock (clients/mock.py)**
Deterministic stand-ins for the LLM, VLM and embedder protocols — the whole
suite and demo run with no network and no API keys.
*Why it matters here:* "works offline" is a tested property, not a slide; real
providers slot in through `.env` when available.

---

## 5. Testing & Eval — numbers you can re-run, not claims

**pytest**
The test runner for the 19-test offline suite (`tests/`) covering ingest,
retrieval, safety, serving, auth, idempotency and eval — driven through ASGI
transport so nothing opens a socket.
*Why it matters here:* every claim in the README maps to a named test, e.g.
`test_incremental_reingest_skips_unchanged`.

**Golden set (`data/qa_golden.jsonl`)**
A fixed exam paper for the system: 38 questions, each with the expected source
section or fault code and a `safety_relevant` flag. Written once, versioned
with the code.
*Why it matters here:* "is it good?" becomes "did it beat last week's score
on the same 38 questions?" — regression, not vibes.

**recall@k (recall@5 = 1.0)**
Of all golden questions, the fraction where the expected source appears in the
top-k retrieved chunks. At k=5 this repo scores 1.0: for every one of the 38
questions, the right section is somewhere in the five candidates.
*Why it matters here:* recall is the floor — if the right chunk was never
retrieved, no amount of clever composing can save the answer.

**Safety-violation rate (zero)**
For safety-relevant golden questions, the fraction where the answer gives
procedural steps without any safety-tagged citation. The gate is `== 0.0`, and
it holds across the whole golden set.
*Why it matters here:* it is the number that says the refusal behavior is not
accidental.

**Eval gates / thresholds (`eval/runner.py`)**
The runner scores the golden set and exits non-zero if any threshold fails
(recall ≥ 0.75, citation precision ≥ 0.80, groundedness ≥ 0.60, safety
violations = 0) — so CI, not a human, catches regressions.
*Why it matters here:* `python -m hvac_copilot.eval` is a one-command health
check that refuses to lie.

**Hybrid ≥ BM25-only (measured, not claimed)**
A regression test runs the golden set in both modes and asserts hybrid matches
or beats BM25-only. On this keyword-heavy corpus BM25 ties at 1.0 — the honest
result, consistent with the RAG_showcase lesson that fusion earns its keep on
paraphrases, not on exact codes.
*Why it matters here:* the repo would rather publish a tie than an
unreproducible win; paraphrase-heavy corpora are where the dense channel pays.

**Determinism (no RNG)**
No random seeds anywhere: hashed embeddings, static corpus, deterministic mock
LLM — so "same input, same output" holds by construction, and the corpus
generator is byte-identical across runs (tested).
*Why it matters here:* eval numbers mean the same thing on your machine, in
CI, and in the video.

---

*80 terms. © 2026 Akshay John Xavier — MIT license.*
