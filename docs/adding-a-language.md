# Adding a language

This guide is for anyone who wants to add a language to DescriVox Agent: you, a friend, or a
coding agent.

Since v1.6.2, adding a language means **adding one file**. No code changes, no build step,
and no new prompts to write.

## In short (users of the .exe — since v1.8.0)

Your own language files live in this folder, which **is never touched when the app is
updated**:

```
%APPDATA%\OmniDescriber\locales\
```

(The folder keeps the app's former name, so files you added before the rename keep working.)

The easiest way there: **Help > Translation Report...**, then answer **Yes** to open the
folder.

1. Copy `en.json` into that folder and rename it to your language code, for example
   `id.json` for Indonesian. (`en.json` is inside the app at
   `_internal\omni_describer_custom\i18n\locales\`.)
2. Change the `_meta` block at the top.
3. Translate the values (the right-hand side); **do not touch the keys**.
4. Restart the app, then choose the language in Settings.

A file for a language that ALREADY exists (for example `ms.json`) in this folder
**corrects** that language line by line — you only write the lines you want to change.
Empty lines are ignored.

## After an update: what is new to translate?

A new version sometimes adds text (a new menu, for example). You do not have to compare
files yourself:

1. Choose your language in Settings.
2. **Help > Translation Report...** — the app says how many lines are not translated yet
   and saves them in `<code>.missing.json` in the same folder, **each line with its English
   text**.
3. Translate those lines, copy them into your `<code>.json`, and restart the app.

The report also lists old keys the app no longer uses (`_obsolete_keys_you_can_delete`);
you can delete them from your file. Until you translate them, missing lines are read in
English, never as key names.

## For developers (source code)

The languages shipped with the app live in `src/omni_describer_custom/i18n/locales/`. Every
text a user sees or hears MUST go through `t("key")` with the key in `en.json` AND
`ms.json` — `test_fixes43` fails if English text is written straight into the UI, or if a
key is not used by any code.

## Language codes

Use two-letter ISO 639-1 codes: `id` Indonesian, `ar` Arabic, `zh` Chinese, `th` Thai,
`ta` Tamil, `hi` Hindi. The file name must equal the code.

## The `_meta` block

This is what makes the language "know about itself":

```json
"_meta": {
  "code": "id",
  "name": "Bahasa Indonesia",
  "english_name": "Indonesian",
  "ai_language": "Indonesian",
  "tts_voice_edge": "id-ID-GadisNeural"
}
```

| Field | Meaning |
|---|---|
| `code` | Must equal the file name |
| `name` | The name in the language itself — this is what NVDA reads in the language picker |
| `english_name` | For developers' reference |
| `ai_language` | The name given to the AI: *"Write EVERY description in Indonesian"* |
| `tts_voice_edge` | The default Edge TTS voice for the language |

To find valid Edge TTS voice names:

```bash
python -c "import asyncio, edge_tts; print([v['ShortName'] for v in asyncio.run(edge_tts.list_voices()) if v['Locale'].startswith('id')])"
```

## Translating

The key on the left, the translation on the right:

```json
"player.load_srt": "Muat SRT...",
```

Three rules:

1. **Never change a key.** `"player.load_srt"` stays the same in every language.
2. **Keep the placeholders.** If the English has `{count}` or `{provider}`, the translation
   must have the same. The tests fail when one is missing — a missing placeholder means a
   number or name never appears.
3. **A partial translation is fine.** Keys not translated yet fall back to English one by
   one. The app never reads a raw key name such as "menu.file" to the user.

### `:one` keys (since v2.0.2)

Some keys have a `...:one` twin, for example `main.log_generated` and
`main.log_generated:one`. The second is used when `{count}` is 1, so English says
"1 description", not "1 descriptions". If your language has no singular/plural form (Malay,
for example), give both the same text. Keep `{count}` in both.

## You do NOT need to translate the AI prompts

The seven audio description presets (`default`, `tight`, `extended`, `foreign`,
`suspense`, `children`, `onscreen_text`) stay in English. The engine adds one instruction —
*"Write EVERY description in Indonesian"* — and the model writes in that language.

This is on purpose: translating seven long prompts for every language would make each new
language hours of work, and a weak prompt translation produces weak descriptions.

(Malay has its own prompt versions because they were written by a native speaker. To do
the same for another language, add a `<code>_default` preset and its siblings in
`prompt_manager.py`.)

## Checking your work

```bash
run_gate.bat
```

`test_fixes24` reports:

- missing keys (and how many)
- keys that do not exist in English (usually typos)
- missing placeholders
- an incomplete `_meta`
- broken JSON files

## A word about quality

The main user of this app is blind. These labels are **read aloud** by a screen reader. An
awkward machine translation is worse than correct English — a user hearing an odd sentence
cannot "scan" the screen to guess what it means the way a sighted user can.

So: machine-translate if you must, but **have a native speaker listen and check** before it
counts as done.

## A complete example (developers)

```bash
cd src/omni_describer_custom/i18n/locales
cp en.json id.json
# edit id.json: change _meta, translate the values
cd ../../../..
run_gate.bat
```

Done. Open the app, go to Settings, and "Bahasa Indonesia" is in the list. (Users of the
.exe: put `id.json` in `%APPDATA%\OmniDescriber\locales\` — see the top of this page.)
