# Checklist (open work and recent phases)

Started 28 Sep 2026. Tick `[x]` only with evidence (test or run output).

Finished phases 1–18 moved to [`archive/checklist-phases-1-18.md`](archive/checklist-phases-1-18.md)
(30 Sep 2026). This file holds everything STILL open and the recent phases. It is the only
place that says what is open.

## Still open (from older phases)

- [ ] Replace the Gemini, OpenRouter, custom and Opus keys if still live (OWNER, in each provider's dashboard)
  _(from: Phase 1 — owner, not an agent)_
- [ ] 5.1 Speech profiles — POSTPONED by the owner (28 Sep 2026)
  _(from: Phase 5 — new features, ask the owner first)_
- [ ] 8.6 (not done — owner's choice) ffmpeg in the Check for Updates menu
  _(from: Phase 8 — small improvements, owner's request 28 Sep 2026)_
- [x] 15.7 (OWNER) Gemini key refused by Google — replace in Settings — DONE 1 Oct 2026: new key, 25/25 requests in a row (23.5)
  _(from: Phase 15 — model comparison, owner's request 29 Sep 2026, v1.8.5)_
- [x] 18.1e Fixed temperature, snap to scene changes — done in 19.B1/19.B2
  _(from: Phase 18 — next steps, owner's order 30 Sep 2026)_

## Phase 19 — B + C + E (chosen by the owner 30 Sep 2026; order E → B → C)

- [x] 19.E1 AGENTS.md: the second 57 became 57b; note "never renumber" (numbers are referenced in code)
- [x] 19.E2 README 1232 → 143 lines (current facts; stale sections removed); 37 releases in
      CHANGELOG.md, 0 history lines lost
- [x] 19.E3 18 finished phases → archive/checklist-phases-1-18.md; 5 open items above; 0 lines lost
- [x] 19.E4 docs/developer-guide.md
- [x] 19.B1 Temperature 0: correct 51 → 83, wrong 24.2% → 16.8% (Gemini), run-to-run spread 21 → 11 — ADOPTED
- [x] 19.B2 Snap to scene changes: no clear gain (wrong 39 → 44 Gemini) — NOT adopted
- [x] 19.C1 "Check the whole video": real run on 3 min of Tears — 22 descriptions, 6 proposals, $0.005;
      FOUND: edits with the same text — now refused
- [x] 19.C2 Agent for Gemini direct — done in 20.6
- [x] 19.R Heard with NVDA: time/cost confirmation read in full, "Checking part 1 of 1", steps,
      "Whole video checked: 2 changes proposed", Esc → "No changes made". FOUND AND FIXED:
      progress said twice (dialog title), "About 1 minutes". Gate 65 suites x2 GATE_ALL_PASS
- [x] 19.S Build 1.9.1 (BUILD_ALL_OK), exe heard by NVDA 10/10, tag v1.9.1, 1.9.0 zip removed

## Phase 20 — 1.9.2 (owner's report 1 Oct 2026)

- [x] 20.1 Custom: unlabelled model box → label "Model name:" (heard by NVDA); base URL without SetLabel
- [x] 20.2 Test Connection button removed (Test this model / Test agent mode do the real check)
- [x] 20.3 "Full-video mode (GLM, Gemini or MiniMax)" → "Send the whole video to the AI (recommended)",
      the hint explains what unticked means (heard by NVDA)
- [x] 20.4 FOUND while listening: Fetch / Test this model / Test agent enabled but dead for Custom → disabled
- [x] 20.5 "Test this model" for every provider: real Gemini 3.8/3.1 (sees + hears), Custom→OpenRouter
      (picture "Red"), wrong key → clear HTTP 401. MiniMax/OpenAI: no key, tested with a fake engine.
      FOUND: Gemini 3.1 Flash-Lite (recommended) missing from the Gemini direct list → added
- [x] 20.6 Agent on Gemini direct: 3.1 Flash-Lite probe passes (3 tools, fixes BLUE→RED, $0.002);
      whole-video check of 3 min of Tears: 19 descriptions, 5 proposals, ~$0.013. 3.8 Flash: 503 then 429 quota
- [x] 20.7 Gemini temperature 0: wrong 14.7% → 14.2% (same), run-to-run spread 23 → 12 — ADOPTED (owner's choice)
- [x] 20.8a Gate 66 suites x2 GATE_ALL_PASS; NVDA AI tab: Custom 9/9, OpenRouter 12/12, Gemini 10/10
- [x] 20.8b Build 1.9.2 (BUILD_ALL_OK), exe heard by NVDA 10/10, tag v1.9.2, 1.9.1 zip removed

## Phase 21 — 1.9.3 (owner 1 Oct 2026: "are the models hard-coded or can they be fetched?")

- [x] 21.1 Fetch models for Gemini: real run with the owner's key, 61 → 12 video models, 3.1 Flash-Lite
      first, prices from the OpenRouter catalog; wrong key → "HTTP 400: API key not valid"
- [x] 21.2 test_fixes57 (fails on the old code 0/4, passes 4/4); MiniMax/OpenAI keep their built-in list (no key)
- [x] 21.3a Gate 67 suites x2 GATE_ALL_PASS; NVDA AI tab Gemini 11/11 ("Fetch models button")
- [x] 21.3b Build 1.9.3 (BUILD_ALL_OK), exe heard by NVDA 10/10, tag v1.9.3, 1.9.2 zip removed
- [x] 21.4 Gemini agent set up for the owner: Test agent mode gemini-3.8-flash PASSED (4 tools, fixes BLUE→RED, $0.0076), recorded in ai.agent_models

## Phase 22 — thinking levels (owner 1 Oct 2026: "did you try high, medium, max?")

Rule: adopt a new level ONLY if it is more accurate (independent judge); if equal, pick the
cheapest/fastest. Record time and cost for every level.

- [x] 22.1 Check the levels each API ACCEPTS — GLM: none refused; Gemini 3.1 Lite has no thinking
      by default, no max; 3.8 Flash refuses minimal; the compat route does not report tokens:
      OpenRouter `reasoning.effort` (GLM), Gemini `thinkingConfig` (whole video),
      Gemini OpenAI-compatible `reasoning_effort` (agent)
- [x] 22.2 model_bench: `@think<level>` variants for GLM and Gemini
- [x] 22.3 (cap 8.3%/4.6%, low 7.1%/2.7%, high 12.0%; max 19 min + empty → the 2000 cap KEPT) GLM 5.3 Flash whole video: current level (2000 tokens) vs the accepted levels,
      4 clips x 3 runs, Gemini judge (+ GLM as a second check)
- [x] 22.4 (default 15.8%, low 12.7%, MEDIUM 9.1%, high 10.7% → medium ADOPTED) Gemini 3.1 Flash-Lite whole video: Google's default vs the accepted levels,
      4 clips x 3 runs, GLM judge
- [x] 22.5 (GLM: cap 8/16, LOW 11/16 2x faster → ADOPTED; Gemini 3.8: 429 quota, not measured) Agent (tools/agent_levels.py): current level vs others, GLM + Gemini — right proposals?
      steps? cost?
- [x] 22.6 Results + numbers in docs/model-comparison.md (clear decision; cost $0.68)
- [x] 22.7 THINKING_BY_MODEL + AGENT_REASONING + retry without thinking when refused (real: 3.8 + minimal → works);
      test_fixes53/55
- [x] 22.8a Gate 67 suites x2 in a row GATE_ALL_PASS (first failure: an odc_probe_ folder left by MY MANUAL SCRIPT, not the app)
- [x] 22.8b Build 1.9.4 (BUILD_ALL_OK), exe heard by NVDA 10/10, tag v1.9.4, 1.9.3 zip removed

## Phase 23 — 1.9.5 (owner: "I topped up Gemini, there should be no problem")

- [x] 23.1 Google documentation read (rate limits, billing, thinking, openai): tiers are per PROJECT
- [x] 23.2 Cause of the 429: the old key was FreeTier, 20/day for 3.8 Flash (quotaId from the full error body)
- [x] 23.3 FIXED: a 429 waits for `retryDelay`/`Retry-After` (max 65 s); a daily limit fails at once with a clear message (test_fixes34)
- [x] 23.4 FIXED (tools): the bench's stale settings copy used the old key; bench counted "stopped at the cost cap" as "kept"
- [x] 23.5 Hard test of the new key: 25/25; agent 3.8 Flash 0/4 fixes, 3.1 Flash-Lite 4/4 (low kept)
- [x] 23.6 Owner's settings: Gemini model → 3.1 Flash-Lite, Test agent mode passed (owner's choice)
- [x] 23.7a Gate 67 suites x2 in a row GATE_ALL_PASS
- [x] 23.7b Build 1.9.5 (BUILD_ALL_OK), exe heard by NVDA 10/10, tag v1.9.5, 1.9.4 zip removed
- [x] 23.8 Agent: empty final answer after the turn limit, and a fix stated without propose_change — done 5 Oct (phase 29.5)

## Phase 24 — tidy the documents (owner 1 Oct 2026)

- [x] 24.1 docs/plan.md: every plan from v1.5.1 to phase 24, open work above
- [x] 24.2 AGENTS.md in English (270 lines, workflow + rules for every agent); CLAUDE.md points to AGENTS.md
- [x] 24.3 docs/pitfalls.md: 88 entries (1–87 + 57b), same numbers, translated; code comments "AGENTS.md pitfall N" → "pitfall N"
- [x] 24.4 Old files to docs/archive/; checklist-v1.7.5 → checklist; every link updated
- [ ] 24.5 User guide, developer guide, README checked against the code; gate x1

## Phase 25 — bugs reported by the owner 2 Oct 2026 ("nothing left behind this time")

Sources: the owner's log (omni_describer.log, 1–2 Oct) + an independent review of the documents against the code.

- [x] 25.1 The owner's REAL settings were polluted: Gemini base_url = http://127.0.0.1:12144/v1beta (a test server) →
      every Gemini job "Cannot connect to host". RESTORED (owner's permission). Cause: 13 test files without their own ODC_CONFIG_DIR
- [x] 25.2 (tests/isolate.py imported FIRST by 71 tests; test_fixes58 fails the gate otherwise; 4 E2E tools sandboxed) Every test file isolates its OWN settings/projects/locales + a guard test (fails if any file does not)
- [x] 25.3 (test_fixes58 catches EVT_DOUBLECLICK on the old code) Open Project CRASHED every time since 1.7.6: wx.EVT_DOUBLECLICK does not exist → EVT_LISTBOX_DCLICK;
      static test: every wx.* name in src exists
- [x] 25.4 (test_fixes49) OpenRouter 413 "Payload Too Large" without a number (Alibaba upstream) was not learned → lower the limit and retry
- [x] 25.5 (test_fixes59: stops within 1 segment; yt-dlp/ffmpeg subtitles too) Cancel ignored during the Whisper transcript (1.5–6 min wait) → transcription can be cancelled
- [x] 25.6 (media/transcript.json, shared with the agent) Transcript made AGAIN on every run (Jantan Miskin 4x, 3–6 min each) → kept in the project
- [x] 25.7 (stderr reader race; exit code included) "video split failed:" with no reason → the real reason + a clear message
- [x] 25.8 (test_fixes60: _ui() + guards; Player/Editor closed properly) Closing the window while processing → crash "MainFrame has been deleted"
- [x] 25.9 (central user_error_text; Gemini upload retried 3x) Raw connection/Gemini errors ("Cannot connect to host ...") → clear bilingual messages
- [x] 25.10 (test_fixes54) Agent F2 "not available" when the model is untested → offer to test now; log the reason
- [x] 25.11 (audit: dialog Cancel not detected AFTER the download in every mode = main cause; audio export, agent, Ask More, Scene Explorer, review, frame/fast mode — test_fixes60/61/62/59) Audit EVERY Cancel button (download, process, compress, split, review, agent, updates, audio export, test model)
- [x] 25.12 (30+ places; job failures now in a message box NVDA reads) Audit every raw error that reaches the user
- [x] 25.13 (output_dir = the export dialog's folder; default glm; ms.json; language box order; 16 document mistakes) Independent review (phase 24): output_dir unused; default provider "gemini" vs "glm"; OpenRouter 429/daily
      quota; English words in ms.json; language box order; 16 mistakes in the guides/README
- [x] 25.15 Owner: the agent must get the CURRENT time; slider "1:04" — position follows the real clock (without VLC
      it fell behind when the timer was late), slider in seconds (arrows 5 s, Page 30 s) read "1:04 of 24:30",
      every agent question carries the position (test_fixes63; old code 0/4)
- [x] 25.16 Owner: "some progress is only read as seconds" — long phases were said once, then the dialog text
      changed EVERY SECOND and NVDA read only "46s". A full sentence every 30 s for every provider
      (phase + % / time left / time elapsed), dialog text every 15 s — REPLACED by 25.17
- [x] 25.17 Owner chose a % BAR ONLY, no periodic speech: AccessibleProgressDialog (a real wx.Gauge NVDA
      knows; the old Windows dialog was DirectUI) with ONE percentage for the whole job: download 0-15, transcript 15-30
      (real Whisper percentage), AI 30-95 (Gemini/MiniMax estimated by time), review 95-99; never goes back.
      Phase-change announcements kept (test_fixes64 6/6; old 0/6)
- [x] 25.18 FOUND while listening: 'Play Video with Existing Descriptions' created a project WITHOUT the video length ->
      slider 0.1 s, playback never ended (old bug). The Player now measures with ffprobe (test_fixes63)
- [x] 25.14a Gate 74 suites x2 GATE_ALL_PASS (before 25.18); heard with NVDA: progress bar "10 percent".."90 percent"
      (tools/nvda_progress_check.py), slider "0:00 of 0:30", Settings (Language on top), Ask More, main
      window 10/10, a real agent session (tools, proposals, decision box, Esc)
- [x] 25.14b Gate 74 suites x2 GATE_ALL_PASS after 25.18; build BUILD_ALL_OK; exe heard by NVDA 10/10;
      tag v1.9.6; 1.9.5 zip removed

## Phase 26 — 1.9.7 (owner 2 Oct 2026)

- [x] 26.1 Scene Explorer said "No AI configured" — cause: no frames YET (a long video loaded at 2 fps,
      >2,800 frames); that one message covered two cases. Now: "still loading" / "no frames" / "no AI";
      a long video loads ~600 frames (test_fixes65)
- [x] 26.2 Agent OR the two older tools (owner's choice): agent ready -> only Agent (F2); untested -> all three,
      passed -> the two older tools go away; no agent -> Ask More + Explore Scene. Follows Settings changes (EVT_ACTIVATE)
      (test_fixes65; old code 0/6)
- [x] 26.4 Owner: shortcuts in the video area — Space play/pause, Left/Right 5 s (Ctrl 10 s, Ctrl+Shift 1 minute) + position said,
      Up/Down video volume 10% (saved; ffplay -volume, VLC audio_set_volume); the video area's name
      lists the keys (test_fixes65)
- [x] 26.5 Video picture keys tested for REAL (tools/nvda_video_keys_check.py, PostMessage to the Player window only):
      focus stays, volume follows every key, NVDA reads each one (3 Oct 2026). Cause of the owner's bug: _announce
      moved the focus to the status line; ffplay restarted on every key (pitfalls 95-97; test_fixes65 11/11)
- [x] 26.6 Tab and F2 in the Player (owner's test 3 Oct): Tab/Shift+Tab leave the Video picture; F2 is now a window
      accelerator (works anywhere); the reason there is no agent is said after Ask More opens (real NVDA test; test_fixes65 14/14)
- [x] 26.3 Gate x2 (GATE_ALL_PASS twice in a row), video keys tested for real + by the owner, build BUILD_ALL_OK,
      exe NVDA 14/14, tag v1.9.7 (3 Oct 2026); 1.9.6 zip deleted with the owner's permission

## Phase 27 — 2.0.0: new name DescriVox Agent (owner 3 Oct 2026)

- [x] 27.1 Name chosen by the owner after web checks of >80 names: **DescriVox Agent** (no other product with that name;
      closest Scriptivox). Capital V, exe `DescriVox.exe`, zip `DescriVox-Agent-<version>-win64.zip`, version 2.0.0
- [x] 27.2 Only the visible names changed (owner's choice): title, About (+ "formerly Omni Describer Custom"), exe/zip,
      build.bat + DescriVox.spec, documents. KEPT: package `omni_describer_custom`, `%APPDATA%\OmniDescriber`,
      `Documents\OmniDescriber`, log — settings, API keys and projects are safe
- [x] 27.3 Gate x2 (GATE_ALL_PASS in a row), build BUILD_ALL_OK (DescriVox-Agent-2.0.0-win64.zip), exe NVDA 14/14 and
      the window found by its title "DescriVox Agent", tag v2.0.0 (3 Oct 2026); 1.9.7 build deleted with the owner's permission
- [x] 27.4 Source-only zip for backup (owner): `Documents\DescriVox-source-backups\DescriVox-Agent-source-v2.0.0.zip`
      (git archive, 182 text files, no exe/keys). AUTOMATIC on every release: build.bat step [6/6]
      `tools/make_source_zip.py` checks every file and fails on binaries/keys (test_fixes66)

## Phase 28 — 2.0.2: Open Project (owner 5 Oct 2026)

- [x] 28.1 "After opening a project, nothing happens" — only a log line. Now (owner's choice: open the Player):
      a project with descriptions -> the Player opens; another project's Player is closed first (never two videos at
      once); an empty project -> a message saying what to do. Both routes (File > Open Project, and choosing the existing
      project for the same video) use `_after_project_opened` (test_fixes68 3/3, real MainFrame + Player)
- [x] 28.2 Real NVDA check (5 Oct): "Open Project dialog" -> Enter -> "Described Video Player – Projek Ujian",
      focus on the Video picture; the main title read as "Descri Vox Agent" (confirms 27.3)
- [x] 28.4 "1 descriptions" -> "1 description" (11 English lines; Malay was already right): `I18n.t()` uses `<key>:one`
      when count = 1 (pitfall 98; test_fixes68 4/4, test_fixes43 7/7); translator guide updated
- [x] 28.3 Release 2.0.2 (5 Oct): gate x2 GATE_ALL_PASS, build BUILD_ALL_OK + first automatic source backup
      (DescriVox-Agent-source-v2.0.2.zip, 195 files), exe NVDA 14/14; tags v2.0.1 (1baa764) and v2.0.2.
      NVDA tool fixed: NVDA no longer says "multi line", so the prompt-box check gave a false alarm

## Phase 29 — 2.1.0: characters + agent 23.8 (owner 5 Oct 2026)

- [x] 29.1 Name rules in every whole-video prompt (core/characters.py CHARACTER_RULES): names heard/shown on screen,
      one fixed label until the name is known, introduce the name once, never invent a name
- [x] 29.2 The cast list carried through EVERY part (GLM): a separate text request after each part (thinking
      capped; failure = cast kept); Gemini/MiniMax: one request at the end. Saved as `characters.json` in the project
      folder — the same file as the agent's (the old {name: description} format is read)
- [x] 29.3 Player > Characters...: Edit/give a name (replaced in every description, asks first), Add, Remove; the user's
      names are never changed by the AI (by_user)
- [x] 29.4 Measured first (tools/cast_bench.py, Tears of Steel + Sintel, GLM + Gemini): name rate Gemini/Sintel 1%->99%,
      GLM/Tears 0%->31%; fewer labels; wrong (GLM judge, 480 samples) 12.5%->14.6% — within noise, none wrong because of names.
      GLM round 2 failed: OpenRouter credit < 1 USD. Owner: on + a Settings > AI switch "Recognise characters by name"
- [x] 29.5 Agent 23.8: an answer like "should say" without propose_change is sent back once; an empty final answer
      is asked again; still empty with proposals -> "N changes waiting" (test_fixes70 5/5)
- [x] 29.6 Real NVDA (keys posted to the test window only): "Characters in this video dialog", list + first
      person, Down -> second person, Tab -> "Edit / give a name... button Alt+E", Enter -> "Character dialog" + name field;
      Settings: "AI Settings tab selected", "Recognise characters by name check box checked". Esc cannot be tested
      with posted keys (pitfall 97) — the owner tried it
- [x] 29.7 The owner tried Characters... with their own keyboard (rename, the N-descriptions question, Esc): all works
- [x] 29.8 Owner's question "can the agent change characters?": the propose_rename tool — ONE proposal "Name X: replace 'label' in N
      descriptions", accept/reject/undo as usual; the name joins the cast as the user's (test_fixes71 3/3)
- [ ] 29.9 GLM round 2 after the owner adds OpenRouter credit
- [x] 29.10 Release 2.1.0 (5 Oct): gate x2 GATE_ALL_PASS (81 suites), build BUILD_ALL_OK + backup
      DescriVox-Agent-source-v2.1.0.zip (201 files), exe NVDA 14/14, tag v2.1.0, push; 2.0.2 zip deleted with permission

## Phase 30 — documentation to GitHub standard, English only (owner 5 Oct 2026)

- [x] 30.1 Owner's choices: every document in English (Malay user guide removed), `doc/` → `docs/` with English
      file names, add SECURITY.md + issue templates + a pull request template, push after the gate
- [x] 30.2 Translated to English: checklist, plan (English only), adding-a-language, model-comparison, CONTRIBUTING,
      archive (4 files; the Malay AI output in sample-output-v1.5.3 kept as evidence), diagrams README; Malay user
      guide removed. New: SECURITY.md, .github/ISSUE_TEMPLATE (bug_report, feature_request, config), PULL_REQUEST_TEMPLATE.
      README rewritten (badges, contents, features, accessibility, requirements, quick start, docs table). Links updated in
      docs, AGENTS, CLAUDE, CHANGELOG, code comments, tests; build.bat/DescriVox.spec bundle `docs`; the smoke test checks
      `docs/user-guide.md`
- [x] 30.3 Gate GATE_ALL_PASS (5 Oct); 0 broken relative links in the documents; pushed. The next build ships `_internal\docs`
- [x] 30.4 Release 2.1.1 (6 Oct): gate x2 GATE_ALL_PASS, build BUILD_ALL_OK (ships `_internal\docs`) + backup
      DescriVox-Agent-source-v2.1.1.zip (205 files), exe NVDA 14/14 (first run lost focus at start-up, second clean),
      tag v2.1.1, push; 2.1.0 zip deleted with permission

## Phase 31 — File > New Project (owner 6 Oct 2026: "what is New Project for?")

- [x] 31.1 Found: New Project made an EMPTY project nothing used (describing made another; Import made its own); it
      stayed in Open Project as "0 descriptions". Owner's choice: make it useful
- [x] 31.2 Now: name → source (Local / YouTube / Direct URL, the same dialogs as the buttons) → "Project X: video chosen"
      spoken, focus to the preset list; Open creates the project with that name (`_pending_project_name`, only for that
      video); a cancel at any step changes nothing (test_fixes72 3/3)
- [x] 31.3 Gate GATE_ALL_PASS (test_fixes21 updated: it asserted the empty project and hung the gate on the new
      source list). Posted-key run: the flow works, focus ends on the presets, "Project X: video chosen" spoken
      (the dialogs were not heard: the test window opened behind). The owner tried it with their own keyboard
      and NVDA (6 Oct): all fine
- [x] 31.4 Release 2.1.2 (6 Oct): gate x2 GATE_ALL_PASS (82 suites), build BUILD_ALL_OK + backup
      DescriVox-Agent-source-v2.1.2.zip (206 files), exe NVDA 14/14, tag v2.1.2, push; 2.1.1 zip deleted with permission

## Phase 32 — documents updated automatically (owner 6 Oct 2026: "next time do all of this automatically")

- [x] 32.1 `tools/check_docs.py`: CHANGELOG/README/AGENTS follow `__version__`; README keeps 3 "What's new"; the plan
      has the release row, every checklist phase, and the right "next phase"; no broken relative links
- [x] 32.2 In the gate (test_fixes73 5/5 — it catches the real 2.1.2 miss from git history) and first in `build.bat`;
      AGENTS release rule + developer guide updated

## Phase 33 — frozen contracts (owner 6 Oct 2026, after reviewing Watch Skill)

- [x] 33.1 `tools/contracts.py`: SHA-256 lock (`contracts/LOCK.json`), versions with reasons (`contracts/CHANGES.md`),
      verdicts VERIFIED / FAILED / INCONCLUSIVE (inconclusive is never a pass). Owner's choice: an agent may change a
      contract only through `freeze`, which records why, and must report it
- [x] 33.2 A. Release contract: `tools/evidence.py` — the gate, the build and the NVDA check record their own results with
      the git tree they ran on; `tools/release_check.py` judges `contracts/release.json`; `tools/tag_release.py` tags only
      on VERIFIED (writes an evidence bundle with its SHA-256). First run: FAILED (v2.1.2 already tagged) with the
      gate/build/NVDA checks INCONCLUSIVE — no evidence recorded yet, as it should be
- [x] 33.3 B. Accessibility contract `contracts/a11y-main.json` (10 controls, from the 2.1.2 exe heard 14/14);
      `nvda_accessibility_check.py` judges every run by it and records the verdict
- [x] 33.4 C. Measurement contract template; `tools/measure_check.py`; `cast_bench.py score --json`. On the characters
      results it says INCONCLUSIVE — the results (5 Oct) are older than any rule (6 Oct), which is the point
- [x] 33.5 test_fixes74 8/8 (weakened contract caught, freeze needs a reason, evidence must be on this code, a11y and
      measure verdicts); `VEDIO DESCRIBER.PY.txt` added to .gitignore so the tree record never includes it
- [ ] 33.6 First release judged by the contract (next version); player and settings accessibility contracts (need a
      listening run)

## Phase 34 — ideas from Watch Skill (owner 6 Oct 2026; release 2.1.3 waits for them)

Each idea: design → freeze a measurement contract (`contracts/measure-<id>.json`) BEFORE measuring → build →
measure → the owner decides. Nothing ships on by default without a VERIFIED measurement.

- [x] 34.1 Honest floor for the agent (F2): `agent.HONEST_FLOOR`, "I cannot see that clearly" + the times looked at.
      Two frozen contracts, both VERIFIED (tools/honest_bench.py, Gemini 3.1 Flash-Lite, 2 runs each):
      easy (absent objects): declined 100% → 100%, correct 75% → 75%; HARD (plausible but unreadable details in Tears
      of Steel and Sintel, truth checked on the frames): declined 100% → 100%, correct 100% → 100%. Today's agent was
      already honest, so the advisory "helps" failed; an apparent +12.5 was a scorer error found by reading the answers
      and fixed (it REMOVED the gain). Owner: keep it, for the one consistent phrase (test_fixes75 4/4)
- [ ] 34.1b The GLM (OpenRouter) agent on the hard set; Ask More (not measured yet, unchanged)
- [ ] 34.2 OCR of on-screen text: a local OCR engine (onnxruntime is already bundled) reads text in sampled frames and
      gives it to the AI like the transcript. Measure on the Excel tutorial, NASA and news clips: wrong rate of
      descriptions about text, cost, time, exe size
- [ ] 34.3 Scene detection for frame selection (frame mode and the agent's search_video): frames at scene changes plus
      near-duplicate removal instead of a fixed interval. Measure: wrong rate, description count, time. (Different
      from the rejected 19.B2, which moved description TIMES to scene cuts.)
- [ ] 34.4 Lessons from the owner's corrections: Editor edits and accepted agent proposals are recorded (old → new) and
      the relevant ones are given to the AI on the next video. Measure: re-describe corrected videos, does the same
      mistake come back less often? (Needs the most design; done last.)
- [ ] 34.5 OpenRouter credit ≥ 1 USD for the GLM measurements (owner; the GLM judge on pictures works without it)
- [ ] 34.6 Release 2.1.3 with the adopted ideas, judged by the release contract (tag only on VERIFIED)

## Phase 35 — the app updates itself (owner 6 Oct 2026)

Owner's choices: download and install by itself; source GitHub Releases; check every time the app opens; two
menu items (Check for Updates = the app, Update YouTube downloader = yt-dlp).

- [x] 35.1 `core/app_update.py`: `releases/latest`, zip checked against `SHA256SUMS.txt`, unpacked next to the app
      (zip slip, other folders and a missing exe refused), folder swap by a cmd script after the app exits, rollback,
      `DescriVox.previous` kept; result said on the next start (`finish_pending`)
- [x] 35.2 `ui/app_update_dialog.py` (named controls, status box takes focus, progress spoken every 25%, notes box,
      Skip this version, download page); start-up offer only when in front and idle; never while processing;
      Settings switch `updates.check_app_at_start`
- [x] 35.3 `tools/release_files.py` in build.bat: `SHA256SUMS.txt` + release notes from the CHANGELOG
- [x] 35.4 test_fixes76 (10/10), the swap run for real against a waiting process (found pitfalls 101 and 102)
- [ ] 35.5 Listen to the dialog with NVDA (needs the PC left alone)
- [ ] 35.6 End-to-end on two real builds (old exe updates itself to a new one from a local test release)
- [ ] 35.7 Owner publishes the first GitHub Release with the zip + SHA256SUMS.txt (2.1.3)

