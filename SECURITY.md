# Security policy

## Supported versions

Only the latest release receives fixes. Please check that you are on the newest version
(see the [tags](https://github.com/lbk2907/DescriVoxAgent/tags) and
[CHANGELOG.md](CHANGELOG.md)) before reporting.

| Version | Supported |
|---|---|
| Latest 2.x release | Yes |
| Anything older | No |

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private vulnerability reporting: open the repository's **Security** tab and
choose **Report a vulnerability**. If that option is not available, open a short public
issue asking for a private contact — without any details of the problem — and we will
reply.

Please include:

- the version (Help > About) and Windows version;
- what an attacker could do, and the steps to reproduce it;
- whether an API key, a file outside the app's folders, or another program is affected.

You can expect a first reply within 7 days. Fixed issues are credited in the CHANGELOG
unless you ask otherwise.

## What counts as a security problem here

- Anything that could expose an **API key**: keys are stored encrypted with Windows DPAPI
  in `%APPDATA%\OmniDescriber\settings.json` and must never appear in logs, URLs, error
  messages, crash reports or exported files.
- Writing, deleting or reading files outside the app's own folders, or running programs
  other than the bundled, hash-checked tools (ffmpeg, ffprobe, ffplay, yt-dlp).
- Downloaded tool updates installed without a matching SHA-256 hash.
- The standalone HTTP API (`python -m video_describer serve`) listening on anything other
  than 127.0.0.1, or accepting paths it should not.

## What is not a vulnerability

- The AI provider seeing the video you send it: that is how the app works. Choose a
  provider you trust.
- Costs charged by a provider for requests you started.

## For contributors

- Never commit keys, `settings.json`, `.env` files or real user projects. `.gitignore`
  blocks the common names, and the release source backup (`tools/make_source_zip.py`)
  refuses any file that looks like a key.
- Tests must use isolated folders (`tests/isolate.py`, pitfall 19) and never a real user's
  settings.
