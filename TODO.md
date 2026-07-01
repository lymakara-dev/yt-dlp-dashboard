# yt-dlp Dashboard — Feature Checklist

Running checklist for transforming the dashboard into a feature-complete yt-dlp UI.
Legend: `[ ]` todo · `[~]` in progress · `[x]` done (backend + frontend + tests + docs).

Each `[x]` means the feature works from **both** backend and frontend, has validation,
tests where appropriate, and docs updated. One feature (group) per commit.

## Foundation (architecture)
- [x] Central `DownloadOptions` model (backend `options.py`, frontend `types.ts`)
- [x] `Job.options` JSON column + lightweight additive SQLite migration runner
- [x] `build_ydl_opts()` refactored to translate the full options model
- [x] Backend test scaffolding (pytest)
- [x] Advanced "Options" UI panel wired into SubmitView (`OptionsPanel.tsx`)

## Phase 1 — Subtitles / Thumbnails / Metadata
- [x] Subtitles: download, auto-subs, select language(s), multiple langs, embed, save separately, convert format
- [x] Thumbnails: download, download all, embed, convert format
- [x] Metadata: info JSON, embed metadata, embed chapters, preserve upload date/uploader/description, comments

## Phase 2 — Audio
- [x] Extract audio only (mp3, aac, opus, flac, wav, vorbis, m4a)
- [x] Audio quality, keep original codec, normalize audio, custom ffmpeg options

## Phase 3 — Advanced format selection
- [x] Full yt-dlp selector support (best/bv+ba/worst/filters/height/fps/codec/HDR/bitrate/ext)
- [x] UI: Basic mode + Advanced (raw selector) mode

## Phase 4 — Playlist
- [x] Entire playlist, range, reverse, random, skip unavailable, flatten, ignore duplicates

## Phase 5 — File organization
- [ ] Output templates, folder templates, auto numbering, archive file, prevent duplicates

## Phase 6 — Browser cookies
- [ ] Import cookies from Chrome/Chromium/Edge/Firefox/Brave/Opera/Vivaldi/Safari + UI selector

## Phase 7 — Authentication
- [ ] Username/password, cookies, OAuth (netrc), age-restricted, membership content

## Phase 8 — Download control
- [ ] Speed limit, retries, retry delay, resume, concurrent fragments, sections/timestamps, max/min filesize

## Phase 9 — Network
- [ ] HTTP/SOCKS proxy, user-agent, custom headers, referer, geo bypass, IPv4/IPv6, bind address

## Phase 10 — Search
- [ ] ytsearch / ytsearchN / playlist search + frontend search page

## Phase 11 — Filtering
- [ ] Filter before download: date, duration, views, likes, title/description regex, size, resolution, ext

## Phase 12 — Post processing
- [ ] Merge, remux, convert, split chapters, SponsorBlock (mark/remove), trim, crop, re-encode, ffmpeg opts

## Phase 13 — Automation
- [ ] Batch URL import, text file import, watch folder, download archive, scheduled downloads

## Phase 14 — Developer features
- [ ] JSON output, raw info extraction, export metadata, progress hooks, plugins, external downloaders (aria2), custom postprocessors

## Phase 15 — UX
- [ ] Better progress bars, speed graph, ETA, retry indicator, queue viz, dark mode, keyboard shortcuts, drag-and-drop, clipboard detection, toasts, responsive

## Wrap-up
- [ ] Full code review + remove dead code
- [ ] README + Developer Onboarding fully updated
