# Project plan — DescriVox Agent

This file gathers EVERY plan made in this project, from v1.5.1 (August 2026) to v2.1.0
(5 Oct 2026), in one readable place. It is the overview: what was planned, when it shipped,
what was decided, and what was rejected after measuring. Item-level evidence (test output,
numbers, NVDA runs) stays in the live [checklist](checklist.md) and its archive
[archive/checklist-phases-1-18.md](archive/checklist-phases-1-18.md). Full measurement tables
are in [model-comparison.md](model-comparison.md); what each release shipped is in
[../CHANGELOG.md](../CHANGELOG.md).

---

## 1. Goals

1. **Accessibility first.** The main user is the owner, who is blind and uses NVDA. Every
   control is named, every status change is spoken, and accessibility is verified by
   LISTENING through NVDA, not by reading code.
2. **Accurate audio description per AD standards** (DCMP, Netflix AD Style Guide v2.1,
   W3C/WAI, ADLAB): describe only what is needed, never repeat what is already audible, short
   enough to speak, at the right moment. Visual accuracy matters more than dialogue (owner,
   29 Sep 2026).
3. **Safe keys and data.** API keys are encrypted (DPAPI), never in URLs, logs or code;
   tests never touch the owner's real settings or projects.
4. **Measured, not assumed.** A new setting is adopted only when the numbers show it is
   better; a model catalog is a claim, a probe is proof.

---

## 2. Open work

Every item still unticked in the checklist, plus known limits recorded in the sources that
have no checklist item.

### 2.1 Checklist items

| ID | Item | Status | Why |
|---|---|---|---|
| Phase 1 | Replace the Gemini, OpenRouter, custom and Opus keys if still live | Waiting for the owner | Done on the provider dashboards; an agent never handles keys. Old keys sat in the XOR backup `settings.json.v1.5.2.bak` (deleted 28 Sep) |
| 5.1 | Speech profiles | Deferred by the owner (28 Sep 2026) | Phase 5 = new features, ask the owner first |
| 8.6 | ffmpeg in the Check for Updates menu | Not done — owner's choice | Check for Updates (v1.7.7) covers yt-dlp only; ffmpeg stays pinned in the build |
| 24.5 | User guide, developer guide and README checked against the code | Open | Partly done by phase 30 |
| 29.9 | Second GLM round of the characters measurement | Waiting for OpenRouter credit (≥ 1 USD) | Round 2 failed with HTTP 402 |

### 2.2 Known limits without an item

| Limit | Source |
|---|---|
| The GLM agent still changes 5 of 8 correct descriptions (level `low`) | model-comparison.md, 22.5 |
| Plan 16.3 listed "check long gaps for missed events"; no measurement of it was found in the sources | archive 16.3, model-comparison.md |
| Whisper: hard cartoon audio still yields a few invented segments; VAD wrongly rejecting real speech would leave a video silently untranscribed | CHANGELOG v1.6.9 |
| Frame mode is not checked by "Check descriptions" | [pitfalls.md](pitfalls.md), pitfall 78 |
| Gemini 3.8 Flash could not be measured for temperature 0 (503, then 429 quota) | model-comparison.md, 20.7 |
| Settings: Esc closes without checking for changes — "deferred" in v1.5.4; later status not recorded | archive/summary-v1.5.4.md |
| Characters: with the cast on, sampled wrong rate 12.5% → 14.6% (within noise, none caused by names); GLM measured once | checklist 29.4 |

---

## 3. Plans by phase

### 3.1 Before numbered phases (v1.5.1 – v1.7.4)

Before 28 Sep 2026 there was no numbered checklist; each release was its own plan. Summary
(details: CHANGELOG.md).

| Release | Date | Summary |
|---|---|---|
| 1.5.1 | < 5 Sep | Cancel everywhere, named projects, full seek bar, TTS fallback |
| 1.5.2 | 5 Sep | Consistent description language; Malay presets fixed |
| 1.5.3 | 5 Sep | Context between parts; 600 s parts; Opus removed |
| 1.5.4 | 8 Sep | Full audit (5 agents): ID bug (data loss), NVDA, DPAPI, key out of URLs; 28 suites |
| 1.5.5–1.5.7 | 17 Sep | Ghost dialog, dead Open button, gate writing real settings, `SetLabel` eating state |
| 1.6.0 | 19 Sep | Prompts follow AD standards; 7 strategy presets (22.7 → 14.0 words/cue) |
| 1.6.1–1.6.4 | 21 Sep | Transcript for the deaf GLM; narration pause; 12-word ceiling; JSON locales; player sound fixed |
| 1.6.5–1.6.7 | 22 Sep | Bundled tools (`core/tools.py`); Prism; resumable downloads; temp housekeeping |
| 1.6.8–1.7.1 | 23 Sep | Word budget per gap; deterministic Whisper (0/7); 30 s frame coverage floor; NVDA pause via audio meter |
| 1.7.2–1.7.4 | 27–28 Sep | Gemini upload fixed; `gemini-3.8-flash` default; audit + 15-min Sintel E2E (no consoles) |

### 3.2 Phases 1–30

Phases 1–18 are in [archive/checklist-phases-1-18.md](archive/checklist-phases-1-18.md);
phases 19 onwards in the [checklist](checklist.md). "—" = no release.

| Phase | Name | Release | Outcome |
|---|---|---|---|
| 1 | Owner (not an agent) | — | XOR `.bak` deleted; key replacement still open |
| 2 | Verify 1.7.4 | 1.7.5 | NVDA every window 16/16; GLM Sintel E2E 121 cues |
| 3 | Tidy | — | AGENTS.md updated; old zips deleted |
| 4 | Bugs + build | 1.7.5 | GLM Cancel <1 s; torch removed (zip 446 → 319 MB); tools pinned + SHA-256 |
| 5 | New features | — | 5.1 speech profiles deferred |
| 6 | Friendly project names | 1.7.6 | `Name (id)/project.db`; 27/27 projects moved; Rename Alt+N |
| 7 | Check for Updates | 1.7.7 | yt-dlp updates with SHA-256; menu `SetTitle` bug found by listening |
| 8 | Small improvements | 1.7.8 | Tests stop using the owner's projects; presets follow locale files |
| 9 | Owner bug | 1.7.9 | API key box no longer vanishes after Show/Hide |
| 10 | Multilingual | 1.8.0 | User languages in `%APPDATA%`; 46 dead keys removed; Translation Report |
| 11 | OpenRouter models + audio per model | 1.8.1 | Fetch models 85 → 65; Test this model; audio per MODEL |
| 12 | D/E/F/G | 1.8.2 (12.8: 1.8.7) | `safe_keys` after the TeamTalk incident; 7 keyboard issues; OpenRouter/GLM default |
| 13 | Long video on the exe | 1.8.3 | YouTube 403 retried; E2E 15/15, 81 cues |
| 14 | Upload progress + NVDA | 1.8.4 | Bar moves during upload; each phase spoken once |
| 15 | Model comparison | 1.8.5 (15.6: 1.8.7) | 7 models × 5 clips: hearing is not more accurate; GLM + Gemini 3.1 Flash-Lite recommended |
| 16 | Accuracy | 1.8.6, 1.8.8 | Ruler (GLM 8% wrong); parts 600 → 300 s (24.5% → 12.9%, 27.5% → 11.8%); full-video default |
| 17 | Release 1.8.6 | 1.8.6, 1.8.7 | Frame mode 204 → 15 descriptions; Esc in Yes/No |
| 18 | Next | 1.8.8, 1.9.0 | Check descriptions (Tears wrong 15 → 7); chosen model now used; Player agent F2 |
| 19 | B + C + E | 1.9.1 | GLM temperature 0 (wrong 24.2% → 16.8%); "Check the whole video"; README 1232 → 143 lines |
| 20 | Owner report | 1.9.2 | Custom labels; Test this model for all; direct Gemini agent; Gemini temperature 0 |
| 21 | Fetch models for Gemini | 1.9.3 | 61 → 12 video models, 3.1 Flash-Lite first |
| 22 | Thinking levels | 1.9.4 | Gemini 3.1 Flash-Lite `medium` 15.8% → 9.1%; GLM agent `low` 8/16 → 11/16; GLM full video keeps the 2000 cap |
| 23 | Gemini 429 | 1.9.5 | 429 waits for `retryDelay`; daily quota fails at once; Gemini 3.1 Flash-Lite agent 4/4; 15.7 done (new key 25/25) |
| 24 | Tidy the docs | — | `plan.md`; AGENTS.md in English + `pitfalls.md` (88 entries, same numbers); `CLAUDE.md`; old files to `archive/` |
| 25 | Owner's bug report | 1.9.6 | Cancel noticed after the download (the main cause); transcript cancellable and kept; Open Project fixed; 413 without a limit; errors in words; tests never touch real settings; slider "1:04"; agent gets the current time |
| 26 | Agent or older tools | 1.9.7 | Scene Explorer: right message, ~600 frames; Player: Agent (F2) OR Ask More + Explore Scene; video-area keys |
| 27 | New name | 2.0.0 | DescriVox Agent: visible names only; settings folders kept; automatic source backup |
| 28 | Open Project | 2.0.2 | Opening a project opens the Player; "1 description" singular |
| 29 | Characters + agent 23.8 | 2.1.0 | One name per person (measured first); Player > Characters...; agent `propose_rename`; agent asks for a proposal instead of words |
| 30 | Documentation to GitHub standard | — | English only; `doc/` → `docs/`; SECURITY.md, issue and pull request templates |

Every release phase closed with gate ×2 GATE_ALL_PASS, build BUILD_ALL_OK, the exe heard
through NVDA, a tag, and the old zip deleted.

### 3.3 Two large plans

**Accuracy plan (phase 16).** Proposed 29 Sep 2026 after the owner said dialogue matters
less than describing the video accurately. Four phases: (1) an automatic ruler calibrated on
hand labels; (2) a wider baseline across drama, cartoon, news/documentary, tutorial + frame
vs full-video mode; (3) fixes — review pass, scene snapping, fixed temperature, gap check;
(4) a Settings toggle. Saved first at the owner's request, then run 29–30 Sep (16.1–16.4,
18.1, 19.B).

**Player agent (phase 18.2).** The owner's idea, 29 Sep 2026; "GO" on 30 Sep. Plan A–E:
A measure tool calling per model (`tools/agent_bench.py`, 4 models pass, $0.063) →
B `core/agent.py` with no UI → C Ask More sends the frame → D F2 UI in the Player →
E tests/NVDA/gate/real run → 1.9.0. Follow-ups: check the whole video (1.9.1), direct
Gemini agent (1.9.2), agent thinking levels (1.9.4), rename characters (2.1.0).

---

## 4. Key decisions

Decisions made by the owner (or accepted by the owner after measuring), with dates where
known.

| Date | Decision |
|---|---|
| v1.5.3 (5 Sep) | Opus provider removed (quota exhausted); use Custom |
| v1.6.0 (19 Sep) | Presets by AD STRATEGY, not genre |
| 23 Sep | Version numbering stops at 9: 1.6.9 → 1.7.0 |
| v1.7.3 (28 Sep) | Gemini default `gemini-3.8-flash` (2.5 closed to new users) |
| 28 Sep | Delete the XOR `.bak`; delete `.audit_scan.sh`; delete test projects (6.0, 6.8, 6.10) |
| 28 Sep | 4.7: cues >20 words — LEAVE (the narration pause handles them) |
| 28 Sep | 5.1 speech profiles deferred; 8.6 ffmpeg in the updates menu not done |
| 28 Sep | Agreed: Check for Updates (phase 7), multilingual (phase 10) |
| 29 Sep | Ask the owner to leave the PC before GUI/NVDA automation |
| 29 Sep | 15.8: GLM stays default; GLM + Gemini 3.1 Flash-Lite listed first as "Recommended" |
| 29 Sep | Visual accuracy > dialogue; accuracy plan saved, waits for the owner |
| 29 Sep | Agent design: F2; video pauses; Accept all / Review one by one / Reject all; Player-session memory; app language; $0.02 cap then ask "continue?"; gated by Test agent mode; no downloading, Settings, deleting or writing external SRT |
| 30 Sep | New-user default = full-video mode; frame mode spaced 4 s (saved mode untouched) |
| 30 Sep | "Check descriptions" OFF by default; choices Auto / Most accurate / Most descriptions / Keep all |
| 30 Sep | Full-video parts 300 s (one-time migration from 600) |
| 30 Sep | Phase 18 order; phase 19 = B + C + E, order E → B → C |
| 1 Oct | Temperature 0 for direct Gemini — for stability (same accuracy) |
| 1 Oct | Phase 22: a new level only if more accurate; if equal, the cheapest/fastest |
| 1 Oct | Owner's Gemini model → 3.1 Flash-Lite (23.6) |
| 3 Oct | New name DescriVox Agent, version 2.0.0; only visible names change; source backup on every release |
| 5 Oct | Opening a project opens the Player |
| 5 Oct | Characters on by default after measuring, with a Settings switch |
| 5 Oct | Every document in English; `docs/`; GitHub community files |

Declined by the owner without measuring (agent design choices): a `listen` tool (sound
identification) and a "hear before accept" preview.

---

## 5. Measured and rejected

Things tried and NOT adopted, with the number. Do not retry without a new measurement.

| Item | Result | Source |
|---|---|---|
| Whisper `beam_size=5` + `vad_filter` (v1.6.8) | Coverage fell to 20%; real speech dropped | CHANGELOG v1.6.8, pitfall 42 |
| Whisper model `small` | 12 hallucinated segments vs 2 (`base`) on 7 different videos | CHANGELOG v1.6.9, pitfall 44 |
| Ask the model to place cues in gaps (prompt) | 56% still in the talky half; the narration pause is used as the mechanism | CHANGELOG v1.6.3, pitfall 14 |
| Raise the token limit for the `foreign` preset | The model just thinks more (15,995/16,000 tokens); the budget was split instead | CHANGELOG v1.6.3 |
| NVDA `speakSsml` synchronous API | Hung on the first call in NVDA 2025.3; an audio meter is used instead | CHANGELOG v1.7.1, pitfall 46 |
| `tasklist` to find the NVDA process | 0.83 s (longer than a 3-word sentence); now ~0.03 s | pitfall 47 |
| Frame mode as the default | 147–204 descriptions a minute on films | model-comparison.md 16.2 |
| 10-minute / 3-minute parts | 10 min: 24.5% / 27.5% wrong; 3 min: 12.1% but slower (696 s vs 605 s) | model-comparison.md 16.2 |
| Gemini 2.5 Flash-Lite, free Nemotron | Invents, and is deaf despite the catalog; Nemotron failed 3/8 runs | model-comparison.md |
| Gemini 3.1 Flash-Lite as the judge | 12/67 false accusations | model-comparison.md 16.1 |
| Snap to scene changes (19.B2) | Gemini judge: wrong 39 → 44; GLM judge 26 → 24 — no clear gain | model-comparison.md 19.B |
| GLM whole-video thinking `low` / `high` / `max` (22.3) | low 7.1% vs cap 8.3% (noise, slower); high 12.0%; max ~15 min on average, one empty — 2000 cap kept | model-comparison.md 22.3 |
| Gemini 3.1 Flash-Lite `low` / `high` (22.4) | 12.7% / 10.7% vs `medium` 9.1% | model-comparison.md 22.4 |
| GLM agent `high` (22.5) | Same 11/16 as `low` but $0.0122 vs $0.0076 | model-comparison.md 22.5 |
| Gemini 3.8 Flash agent (22.5b) | 0/4 fixes, ~10× the cost of 3.1 Flash-Lite | model-comparison.md 22.5b |
| 3.1 Flash-Lite agent `medium` / `high` | 5/8 and 6/8 vs `low` 6/8, costlier — `low` kept | model-comparison.md 22.5b |
| Agent instructions v1 (without "only if CLEARLY wrong") | 3 models edited correct descriptions 6/6 times | model-comparison.md, Phase A |

---

## 6. How to add a plan

1. A new phase continues the numbering: the next one is **Phase 31**. Never renumber.
2. Write a short entry here (phase, name, reason, date, who asked) and the detailed items
   in the [checklist](checklist.md) (`31.1`, `31.2`, ...).
3. Tick `[x]` only with evidence: test output, numbers, a real run, or NVDA heard.
4. Measure before adopting: a new setting or model goes in only when the numbers are better
   (independent judge, several different clips, several runs). Record the numbers in
   [model-comparison.md](model-comparison.md); rejected ones go in section 5 above.
5. New features: ask the owner first. GUI/NVDA work: ask the owner to leave the PC.
6. When a release ships: update the phase table here, CHANGELOG.md and the AGENTS.md status.
