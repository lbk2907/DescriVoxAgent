# Video model comparison and measurements

Started 29 Sep 2026. The owner's question: should models that HEAR the audio describe more
accurately? Tested with the app's own engine (`tools/model_bench.py`), not by reading
catalogs. Total cost of the first round: **$0.26** on OpenRouter.

## Method

Five genuinely different clips (pitfall 44), 50–60 s each:

| Clip | Content |
|---|---|
| truth | Built here: 8 visual events + a knock (0:20), a voice "The password is pineapple" (0:31), a bell (0:45) at KNOWN times |
| sintel_dialogue | Sintel 1:50–2:50, English dialogue + action |
| ocong | Indonesian cartoon, dense dialogue |
| bm_news | AWANI Ringkas (Astro AWANI), Malay news |
| bbb_music | Big Buck Bunny 2:00–3:00, music, no speech |

Each model: 2 runs × 5 clips with the `default` preset and a transcript (as in the app),
plus a **hearing test** on the truth clip WITHOUT a transcript. Accuracy on the real clips
was checked BY EYE: the frame at each description's time compared with its text (run 1).

## Results

| Model | Hears? (knock / bell / sentence) | Truth events | Visual accuracy (eye check) | Problems |
|---|---|---|---|---|
| **GLM 5.3 Flash** (default) | ✗ deaf; **invents** 3 "dripping" sounds | 8/8, timing error 0.6 s | **Joint best** — Sintel 6/6, Malay news 3/3, Ocong 7/7 | 17% of descriptions >12 words; misidentifies the BBB character ("red rabbit") |
| **Gemini 3.1 Flash-Lite** | bell ✓ sentence ✓ | 8/8, 1.5 s | **Very good** — Sintel 4/5, Malay news 3/3, Ocong 6/6 | Cheapest and fastest of those that hear; 0% long descriptions |
| Gemini 3.8 Flash | bell ✓ (called a "car horn") sentence ✓ | 7.5/8, **0.1 s** | Accurate but **too few** (Sintel 3, Ocong 2 descriptions/min) | Expensive (5× GLM) |
| Qwen3.8-Omni-Flash | bell ✓ sentence ✓ | 8/8, 1.4 s | Good, but writes **paragraphs** (35 words in one description) | "He stands" (actually sitting) |
| MiMo v2.6 Flash | knock ✓ bell ✓ sentence ✗ ("The pet project have a bomb") | 7.5/8 | Timing **off** (handcuffs at 0:22, really 0:45; city 14 s early) | Cannot read AV1; slowest (134 s) |
| Gemini 2.5 Flash-Lite | **✗ no sound at all** although the catalog says yes | 7/8 | **Invents** — "playing a flute", "a large hand grabs his arm" | 37 descriptions in 60 s (unspeakable) |
| Nemotron Omni (free) | could not be tested (server limits) | 8/8, **10.4 s** | Average | 3/8 runs failed; broken time format ("-00:01]") |

## The answer

**Hearing does NOT make descriptions more accurate in this app.** The deaf GLM is as
accurate as, or more accurate than, every model that hears. Three reasons:

1. The app already gives EVERY model a transcript of the speech — a deaf model knows what
   is said.
2. AD standards forbid describing what the listener already hears (dialogue, music,
   sounds). The advantage of hearing is rarely used.
3. Visual accuracy and timing depend on the model's VISION.

Where hearing DOES help: when the transcript fails (see bug 1 below) or when an off-screen
sound changes the meaning of a scene.

**Best candidates:** GLM 5.3 Flash (stays default: accurate, cheap) and **Gemini 3.1
Flash-Lite** (hears, accurate, fast, cheap, short descriptions). Do not use Gemini 2.5
Flash-Lite (invents, deaf although it claims to hear) or the free Nemotron (unstable).

## App bugs found by this test (fixed in v1.8.5)

1. **The Ocong transcript was EMPTY.** faster-whisper gives a compression ratio per 30 s
   window; "Bra, bra, bra, bra" made the whole window 2.79 and 8 real sentences were
   dropped. Now judged per sentence.
2. **YouTube picked AV1 + Opus**; MiMo and Nemotron cannot open it. Downloads now prefer
   H.264 + AAC (same resolution). Confirmed: MiMo fails on AV1, 16 descriptions on H.264.
3. The owner's (direct) Gemini key was refused by Google ("API key not valid") — not an app
   bug; the key had to be replaced in Settings.

## Running it again

```
python tools/model_bench.py make-clips
python tools/model_bench.py run --runs 2
python tools/model_bench.py score
python tools/model_bench.py frames --run 1
```

## The accuracy ruler (phase 16.1, 29 Sep 2026)

`python tools/model_bench.py measure` — ANOTHER model judges every description against 4
frames around its time (-0.5 s to +4 s): correct / partial / wrong.

**Calibrated first, twice:**

| Label set | GLM as judge | Gemini 3.8 as judge |
|---|---|---|
| 99 hand labels (`tools/bench_labels.json`, rechecked after the judge showed 10 of my labels were wrong) | 12/13 wrong caught, 0/63 false accusations | 13/13, 1/63 |
| 30 **blind** labels (`tools/bench_labels_blind.json`, labelled BEFORE the judge saw them) | 1/1, 0/20 false accusations | 0/1, 1/20 |

Gemini 3.1 Flash-Lite was rejected as a judge (12/67 false accusations). "Correct" vs
"partial" is fuzzy even between people (~70% agreement) — **the number to trust is the
WRONG rate.**

**Results on all 488 descriptions (2 runs × 5 clips), GLM judge, cost $0.025:**

| Model | Wrong | Wrong (Gemini 3.8 judge) |
|---|---|---|
| Qwen3.8-Omni | 7.2% | 24.6% |
| **GLM 5.3 Flash** | 8.0% | **13.8%** |
| Gemini 2.5 Flash-Lite | 11.0% | – |
| Gemini 3.8 Flash | 11.7% | – |
| Gemini 3.1 Flash-Lite | 14.5% | – |
| Nemotron | 20.7% | – |
| MiMo | 22.2% | – |

Judges differ in strictness (Gemini is harsher), so compare models with the SAME judge. GLM
does not favour itself: Gemini rates GLM better than Qwen. **Baseline for phase 3: about 1
in 10 GLM descriptions is wrong or mistimed.** The GLM judge costs ~$0.00005 per
description — cheap enough for a review pass inside the app.

## Phase 16.2 — a wider baseline (29–30 Sep 2026)

New genre clips (60 s): **Tears of Steel** (live-action drama, Blender CC-BY), **NASA Our
Planet, Our Home** (documentary, public domain), **Microsoft Excel Basics Tutorial**
(PiTutorial, Malay screen recording). Long video: the full 14:48 Sintel. Judge: GLM (the
16.1 ruler).

### Genres on short clips — accuracy is not the problem

| Model | Drama | Documentary | Tutorial |
|---|---|---|---|
| GLM 5.3 Flash | 0/10 wrong | 0/16 | 0/16 |
| Gemini 3.1 Flash-Lite | 1/12 | 0/11 | 1/13 |

### Four bugs found (fixed in v1.8.6)

1. **Missing speech gaps.** Whisper stretched every segment to the next one: Tears claimed
   58.5 s of speech in 60 s (29.0 s by words). Both models wrote ONE description for a
   minute of robots and people. `word_timestamps=True`: GLM 12 → **30** descriptions
   (4 runs), **0 wrong** before and after.
2. **Provider size limits behind OpenRouter.** Google AI Studio refuses bodies >20 MB;
   Gemini 3.1 Flash-Lite FAILED on the full Sintel (413). One GLM upstream is limited to
   **8 MiB** although other servers accept 29 MB parts — jobs could fail at RANDOM. The
   limit is now known for `google/*`, and other limits are LEARNED from the 413 error, then
   the part is compressed and sent again.
3. **A 504 inside a 200 response** killed the whole job after 15 minutes (every finished
   part thrown away). It is now retried like other 5xx.
4. After fix 2: Gemini 3.1 Flash-Lite succeeds on the full Sintel (77 descriptions).

### Long video: the part length decides the accuracy

| GLM, Sintel 14:48 | Wrong | Time | Note |
|---|---|---|---|
| 10-minute parts (default) | **24.5%** | 978 s | part 1 ~30% wrong, part 2 (4.8 min) 14% |
| 5-minute parts | **12.9%** | **605 s** | 141 s gap = end credits |
| 3-minute parts | **12.1%** | 696 s | 87 s gap = end credits |

The mistakes of long parts are the RIGHT event at the WRONG time (a 10-minute part is
compressed to 360p; the model cannot pin the second). 60 s clips: 0–8% wrong.

**Confirmed on a SECOND long film (full Tears of Steel, 12:14):** 10-minute parts **27.5%**
wrong (+ an 85 s hole with no description at the end of part 1), 5-minute parts **11.8%**.
The app default is now 300 s (v1.8.6).

### Frame mode (then the new-user default) — not suited to films

| Model | 60 s clip | Descriptions | Words/description | Markdown junk | Wrong | Time |
|---|---|---|---|---|---|---|
| Gemini 3.1 FL | Tears | **204** | 12 | 0% | 3% | 783 s |
| Gemini 3.1 FL | Malay news | **176** | 16 | 0% | 11% | 501 s |
| Gemini 3.1 FL | Sintel | **147** | 10 | 0% | 10% | 417 s |
| Gemini 3.1 FL | Big Buck Bunny | 98 | 28 | 1% | 15% | 294 s |
| Gemini 3.1 FL | Ocong | 24 | 17 | 4% | 17% | 75 s |
| GLM 5.3 Flash | Excel | 31 | **41** | **51%** | 6% | **856 s** |

Every frame that survives deduplication becomes a 1-second description — 2–3 a second,
impossible to speak. Not more accurate than full-video mode. GLM takes ~20 s per frame; the
GLM film runs were stopped (estimated 4 hours).

## Phase 16.3 — a review pass (30 Sep 2026)

The reviewer (GLM) sees 12 frames from 20 s before to 20 s after each description and
answers where it is MOST clearly visible, or "none". Tested on existing results (Sintel
14:48 + Tears 12:14, 5-minute parts, 209 descriptions) — `model_bench.py review` — and
measured by an INDEPENDENT judge (Gemini 3.8) as well as GLM. Review cost ~$0.014 per film.

| Option | Descriptions | Wrong (Gemini) | Correct (Gemini) | Wrong (GLM) |
|---|---|---|---|---|
| No review | 209 | 39 (18.7%) | 106 | 26 (12.4%) |
| A: v1 — move to the clearest frame, drop "none" | 198 | 27 (13.6%) | **113** | 18 (9.1%) |
| B: v2 — keep if already visible where it is, drop "none" | 187 | **23 (12.3%)** | 107 | **15 (8.0%)** |
| C: v2 without dropping | 209 | 32 (15.3%) | 112 | – |

Findings:
- Most mistakes are the RIGHT event at the WRONG time, so moving the time helps. v1 fixed
  17 wrong descriptions in Sintel but broke 9 correct/partial ones (moving ones already
  right to a "clearer" frame); in Tears it was a net loss (5 fixed, 7 broken).
- v2 first asks "is it visible where it is?" — only 22 moved (not 98).
- v2 "none" (dropped): 9 wrong, 8 partial, 5 correct — dropping also loses good
  descriptions.
- Small sample: A vs B (27 vs 23 wrong) is within noise. What is certain: EVERY option cuts
  wrong descriptions by ~20–40% compared with no review, at a small cost.
- OpenRouter credit nearly gone ($0.80) — the fixed-temperature and scene-snap tests were
  not run yet.

## Agent mode — phase A: can the models drive an agent? (30 Sep 2026)

`tools/agent_bench.py`: the Player agent's real task on Tears of Steel, through
OpenAI-style tool calls (current_position, read_descriptions, look_at, look_between,
propose_change). Two tasks: a description judged WRONG (must be fixed) and one judged
CORRECT (must be left alone). 2 runs each. Total cost $0.063.

**Protocol:** all 4 models — 32/32 runs used real tool calls, looked at frames BEFORE
proposing, valid arguments. The catalog was right this time.

**Behaviour (instructions v2: "only if CLEARLY wrong; look at several seconds"):**

| Model | Fixes the wrong one | Leaves the correct one | Note |
|---|---|---|---|
| Gemini 3.1 Flash-Lite | 2/2 | 2/2 | fast (~7 s) |
| Qwen3.8-Omni | 2/2 | 2/2 | ~13 s |
| GLM 5.3 Flash | 2/2 | 0/2 | the "correct" one changed reasonably (moved 2.6 s to the real flash / removed "blinding") — over-careful, not wrong |
| Gemini 3.8 Flash | 0/2 | 2/2 | on the "wrong" task it did NOT answer at all (8-turn limit) |

Instructions v1 (without the strict condition): GLM, Gemini 3.1 FL and Qwen edited the
correct description 6/6 times — the "clearly wrong" condition matters.

For phase B: (1) when the turn limit is reached, the agent MUST be made to give a final
answer; (2) "Test agent mode" passes on protocol + looking first + valid arguments + a final
answer — not on the model's opinion.

## Phase 19.B — fixed temperature and scene-change snapping (30 Sep 2026)

**Temperature 0 — ADOPTED (v1.9.1).** GLM 5.3 Flash, full-video mode, 4 different clips
(Tears, NASA, Malay news, Sintel dialogue) x 3 runs per setting, run together with the same
code (`@tdef` vs `@temp0`):

| | Server default temperature | Temperature 0 |
|---|---|---|
| Descriptions (12 runs) | 95 | 119 |
| Wrong — Gemini judge | 23 (24.2%) | **20 (16.8%)** |
| Correct — Gemini judge | 51 | **83** |
| Wrong — GLM judge | 20 (21.1%) | **11 (9.2%)** |
| Run-to-run difference in count (total) | 21 | **11** |

An example of the default temperature's instability: Malay news gave 3, 15, 14 descriptions
on three runs (temperature 0: 18, 16, 16). Now `GLMProvider.TEMPERATURE = 0` for every
OpenRouter model; Gemini direct unchanged (not measured yet). Cost $0.08 + judging $0.29.

**Snap to scene changes — NOT adopted.** Each description moved to the nearest scene cut
within ±2 s (ffmpeg scene > 0.3), on the full Sintel and Tears: Gemini judge — correct
106 → 113 but wrong 39 → 44; GLM judge — wrong 26 → 24, correct 125 → 126. No clear gain,
so not included (rule: keep only what raises the numbers). `model_bench.py snap` stays for
later tests. Cost $0.13.

## Phase 20.7 — temperature 0 for Gemini direct (1 Oct 2026)

Gemini 3.1 Flash-Lite with the owner's Gemini key, the same 4 clips (Tears, NASA, Malay
news, Sintel dialogue) x 3 runs, `@tdef` vs `@temp0`, scored by the GLM judge (Gemini does
not judge itself; `model_bench.py measure --direct`):

| | Google default temperature | Temperature 0 |
|---|---|---|
| Descriptions (12 runs) | 245 | 267 |
| Wrong — GLM judge | 36 (14.7%) | 38 (14.2%) |
| Correct — GLM judge | 160 | 172 |
| Run-to-run difference in count | 23 | **12** |

Accuracy did NOT change; stability improved (Tears 15, 8, 14 → 17, 17, 16). The owner chose
temperature 0 for the stability (`GeminiProvider.TEMPERATURE = 0`). Gemini 3.8 Flash could
not be measured: repeated 503 "high demand", then the free key's 429 quota. Cost: judging
$0.04 (OpenRouter); the Gemini runs on the owner's key.

## Phase 22 — thinking levels (1 Oct 2026)

**22.1 Accepted levels** (small text calls, not guesses):

- OpenRouter GLM 5.3 Flash: `reasoning.effort` minimal/low/medium/high/xhigh/max accepted;
  `none` REFUSED ("Reasoning is mandatory").
- Gemini direct, `thinkingConfig.thinkingLevel`: 3.1 Flash-Lite does NOT think by default;
  low 115, medium 309, high 460 tokens; `max` does not exist. 3.8 Flash ALREADY thinks by
  default (926 tokens); low 464, high 3746; `minimal` REFUSED for that model.
- Gemini OpenAI-compatible (`reasoning_effort`, the agent's route) does not report thinking
  tokens — the effect cannot be seen.

**22.3 GLM 5.3 Flash full video**, 4 clips x 3 runs:

| Level | Descriptions | Wrong (Gemini judge) | Wrong (GLM judge) | Average time |
|---|---|---|---|---|
| 2000-token cap (app) | 108 | 9 (8.3%) | 5 (4.6%) | 84 s |
| low | 112 | 8 (7.1%) | 3 (2.7%) | 101 s |
| high | 75 | 9 (12.0%) | 2 (2.7%) | 98 s |
| max (2 runs) | 5 | — | — | **901 s, 1 empty** |

The cap/low difference is only 1–2 descriptions (chance range) and low is slower: the
2000-token cap is KEPT. `max` breaks things (NASA: 644 s, 0 descriptions — the v1.6.3
pattern); stopped after 2 runs.

**22.4 Gemini 3.1 Flash-Lite full video**, 4 clips x 3 runs, GLM judge:

| Level | Descriptions | Wrong | Correct | Run spread | Average time |
|---|---|---|---|---|---|
| default (no thinking) | 273 | 43 (15.8%) | 168 | 3 | 61 s |
| low | 228 | 29 (12.7%) | 152 | 14 | 45 s |
| **medium** | 232 | **21 (9.1%)** | 156 | 4 | **36 s** |
| high | 243 | 26 (10.7%) | 164 | 3 | 59 s |

`medium` ADOPTED for this model only (`THINKING_BY_MODEL`).

**22.5 Agent** (`tools/agent_levels.py`, the app's real agent engine, 4 wrong + 4 correct
descriptions agreed by TWO judges, x 2 runs):

| GLM 5.3 Flash | Right answers | Wrong fixed | Correct kept | Cost | Average |
|---|---|---|---|---|---|
| 1000-token cap (app) | 8/16 | 7/8 | 1/8 | $0.0086 | 59 s |
| **low** | **11/16** | 8/8 | 3/8 | $0.0076 | **25 s** |
| high | 11/16 | 8/8 | 3/8 | $0.0122 | 36 s |

`low` ADOPTED for the GLM agent (`AGENT_REASONING`). The Gemini 3.8 Flash agent could not be
measured: the free key's 429 quota. A weakness remains: the agent still changes 5 of 8
correct descriptions.

Total cost of phase 22: $0.68 OpenRouter (Gemini judging $0.40) + free Gemini quota.

### Phase 22.5b — the Gemini direct agent (1 Oct 2026, after the owner fixed billing)

The old key was on the FREE tier: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, 20
requests a day for 3.8 Flash — one agent session uses 5–10. New key: 25/25 requests in a
row passed. (The first run after that still failed because `model_bench` used an OLD COPY of
the settings — it is now copied again when the real settings are newer.)

| Gemini direct | Right answers | Wrong fixed | Correct kept | Cost / question | Average |
|---|---|---|---|---|---|
| 3.8 Flash, low, $0.02 cap (app) | 0/8 decided | — | — | $0.02 (cap) | 29 s |
| 3.8 Flash, low, $0.10 cap | 4/8 | **0/4** | 4/4 | $0.029 | 34 s |
| **3.1 Flash-Lite, low (app)** | **6/8** | **4/4** | 2/4 | **$0.0026** | **10 s** |
| 3.1 Flash-Lite, medium | 5/8 | 4/4 | 1/4 | $0.004 | 13 s |
| 3.1 Flash-Lite, high | 6/8 | 4/4 | 2/4 | $0.0048 | 15 s |

3.8 Flash kept looking (8 turns in a row) without deciding, up to the cost cap; when allowed
more, it sometimes STATED a fix in its answer but did not call `propose_change` (fixed in
v2.1.0, checklist 29.5). 3.1 Flash-Lite: the current `low` level kept. The owner switched the
Gemini model to 3.1 Flash-Lite. Cost (catalog price estimate): about $1.3 of Gemini credit.

## Phase 29.4 — characters: one name per person (5 Oct 2026)

`tools/cast_bench.py`: the app's own providers on two full films with named people, with
the v2.1.0 character rules + cast ("on") and without ("off"): **Tears of Steel** (12 min,
Celia and Tom heard in the dialogue) and **Sintel** (15 min, Sintel and Scales). GLM splits
each film into 5-minute parts (does the cast carry across parts?); Gemini watches the whole
film.

Scored on the text: **name rate** = share of the lines about a person that use a name heard
in the film; **labels** = different generic phrases for people (fewer = more consistent).
Accuracy: 40 descriptions per run sampled evenly, the validated GLM judge (16.1). Gemini 2
rounds; GLM 1 round (round 2 refused with HTTP 402: OpenRouter credit below 1 USD).

| Provider | Film | Name rate off → on | Labels off → on | Wrong off → on |
|---|---|---|---|---|
| Gemini 3.1 Flash-Lite | Sintel | **1% → 99%** | **7 → 2.5** | 15.0% → 15.0% |
| Gemini 3.1 Flash-Lite | Tears | 1% → 3% | 9.5 → 8 | 11.2% → 15.0% |
| GLM 5.3 Flash | Sintel | 69% → 50% | 9 → 8 | 17.5% → 12.5% |
| GLM 5.3 Flash | Tears | **0% → 31%** | **23 → 17** | 5.0% → 15.0% |
| **Total** | | | | **12.5% → 14.6%** |

The names used were right ("A young woman, Celia, faces Thom on the bridge"); no name was
invented. Overall 5 more of 240 sampled descriptions were judged wrong — within run-to-run
noise, and none of the wrong verdicts was about a name (all were ordinary visual or timing
misses). Owner's decision: ON by default, with a Settings > AI switch "Recognise characters
by name". Found while measuring and fixed: the cast update came back empty when GLM spent
its budget thinking (now capped), and names came back in CAPITALS (now normalised; NVDA may
spell capitals).

## Phase 34.1 — the honest floor for the agent (6 Oct 2026)

Idea from Watch Skill: when the agent cannot see what is asked, it should say so instead of
guessing. `tools/honest_bench.py` runs the app's own agent (Gemini 3.1 Flash-Lite) with the
floor off and on, 2 runs each, judged by contracts frozen before each run.

| Round | Questions | Declined when not there: off → on | Correct when there: off → on |
|---|---|---|---|
| 1 (`measure-honest-floor`) | the truth clip + Sintel dialogue: 8 absent objects, 4 visible facts | 100% → 100% | 75% → 75% |
| 2 (`measure-honest-floor-2`) | Tears of Steel and Sintel at given moments: 8 plausible but unreadable or absent details (blurred plate, carton brand, T-shirt writing, eye colour in the dark...), 8 visible ones; truth checked on the frames | 100% → 100% | 100% → 100% |

Both VERIFIED; the advisory "it helps by 10 points" failed both times, because today's agent
was already honest. Round 2 first showed +12.5 points: reading the answers showed the scorer
had missed "it is not possible to determine" as a refusal; fixed, the gain disappeared. The
owner kept the floor for the one consistent phrase ("I cannot see that clearly" + the times
looked at). Not measured yet: the GLM agent, and Ask More. Cost: about $0.15 of Gemini credit.

