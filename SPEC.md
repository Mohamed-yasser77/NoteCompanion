# SPEC: YouTube Learning Notes Workflow

> Status: v0.3 — fully automated pipeline with video classification.
> Instruction to the coding agent: read this file before every task. Do not build anything listed under "Not in v1". If something here is ambiguous, ask before coding.

## 1. Goal

While I watch a YouTube video to learn something, the system turns the video's content into structured, timestamped notes I can review later without re-watching. Each day, a Google Calendar event records what I learned and links to the notes.

## 2. Type of system

An **automated background pipeline**. The system runs without any user interaction. When a YouTube video loads, the extension detects it, the backend classifies it, and if it is educational the full notes pipeline runs automatically. The user only ever opens the popup to *view* results, never to trigger them.

## 3. Pipeline

```
YouTube video ID (detected automatically on page load / SPA navigation)
   -> [0] Classify video (educational / borderline / entertainment)
          - Educational or borderline -> continue
          - Entertainment -> stop silently, badge shows ⏭️
   -> [1] Get transcript (timestamped)
   -> [2] Chunk by time
   -> [3] LLM: notes per chunk
   -> [4] LLM: short summary of the whole video
   -> [5] Save note file (markdown, push to GitHub)
   -> [6] Create/update the day's calendar event with summary + note link
```

### Step details

| Step | Input | Output | Notes |
|---|---|---|---|
| 0 Classify | video ID | `educational` \| `borderline` \| `entertainment` | Call YouTube Data API v3 to get `categoryId`. Categories 27 (Education) and 28 (Science & Technology) → `educational`. Other categories (e.g. gaming, music, entertainment) → `entertainment`. Any category that could be learning-related (tech podcast, documentary, how-to, news) → `borderline`. Both `educational` and `borderline` proceed through the pipeline. |
| 1 Transcript | video ID | list of `{start_seconds, text}` | Use captions only. If none exist, fail with a clear error (no audio fallback in v1). |
| 2 Chunk | transcript list | list of chunks, ~4 min each | Keep each chunk's start/end time. If video is shorter than one chunk, treat as a single chunk. Never split mid-sentence; break at the nearest caption boundary. |
| 3 Notes | one chunk | key concepts, definitions, examples (bullets) | Must only use content from the chunk. No outside facts. |
| 4 Summary | all chunk notes | 2-3 line summary + topic title | Used for the calendar event. |
| 5 Save | notes + metadata | `YYYY-MM/<video_id>.md` committed to GitHub notes repo | Overwrite the file and `git push` on re-run; never create a duplicate file. The GitHub web URL (`https://github.com/<user>/<notes-repo>/blob/main/YYYY-MM/<video_id>.md`) is used as the note link everywhere — it is phone-accessible. |
| 6 Calendar | summary + note link | one all-day event per day | Before creating, search existing events for that date with title prefix `Learned:`. If found, patch it. If not found (e.g. deleted or first run on new machine), create a new one and store the event ID locally. |

## 4. Note file format

```markdown
# <Video title>
Source: https://youtu.be/<video_id>
Date learned: YYYY-MM-DD
GitHub: https://github.com/<user>/<notes-repo>/blob/main/YYYY-MM/<video_id>.md

## Summary
<2-3 lines>

## Notes
### [MM:SS] <chunk topic>  (link: https://youtu.be/<video_id>?t=<seconds>)
- point
- point
```

Every chunk heading must link to the exact timestamp in the video. The GitHub URL in the front-matter is the canonical shareable link used in the calendar event.

## 5. Calendar event format

- One **all-day** event per date.
- Title: `Learned: <topic 1>, <topic 2>`
- Description: for each video that day, 2-3 lines of summary followed by the GitHub note link.
- **Idempotency:** Before creating, call `GET /events` filtered to that date and search for a title starting with `Learned:`. If found, patch it. If not found, create a new event. This ensures correctness even when the app is run from a different machine or after the event is manually deleted.
- Store the event ID locally after every create or patch; use it as a fast-path shortcut on the next run.

## 6. Tech stack

- **Extension:** Chrome Manifest V3 (content script + popup).
  - Content script: watches for page load and SPA navigation, extracts video ID, fires `POST /classify` to the backend immediately.
  - Popup (read-only): opens when you click the icon. Shows the classification result, pipeline status, and the generated notes for the current video. Never triggers the pipeline — it only displays results.
  - Icon badge states: `⏳` (pipeline running), `✅` (notes saved), `⏭️` (skipped — entertainment), `❌` (error).
- **Backend:** Python 3.11, FastAPI. All API keys live here only. Started via a cross-platform launcher script (`start.sh` on macOS/Linux, `start.bat` on Windows) that the user runs once per session. The backend must be running for the extension to work. OS-level auto-start (systemd, launchd, Task Scheduler) is out of scope for v1 and may be added in Phase 6.
- **LLM:** Gemini 1.5 Flash via API. Wrapped behind a single function — the model can be swapped by changing one file.
- **Transcripts:** `youtube-transcript-api` for the Phase 1 prototype (unofficial; may break). Keep all transcript code in one module.
- **Classification:** YouTube Data API v3 (`videos.list?part=snippet` → `categoryId`). No LLM call needed for classification. Borderline categories are treated as educational.
- **Storage:** GitHub private notes repository. Notes are saved as `YYYY-MM/<video_id>.md` and pushed after every write. The GitHub web URL is used as the canonical note link (phone-accessible).
- **Auth:** Google OAuth for Calendar (Phase 5). YouTube Data API uses an API key (no OAuth needed for public video metadata). GitHub push uses a Personal Access Token — both stored in `.env` (backend only).

### Module layout

```
backend/
  classify/      # YouTube Data API v3 call — categoryId → label
  transcript/    # youtube-transcript-api isolation — only module allowed to call it
  pipeline/      # orchestration: calls steps 0-6 in order
  llm/           # single LLM wrapper; all Gemini calls go here
  calendar/      # Google Calendar OAuth + event CRUD
  notes/         # note file rendering, GitHub push logic
  api/           # FastAPI route definitions
extension/
  content/       # content script: video ID detection, SPA nav detection, auto-trigger
  popup/         # popup UI — read-only display of status and notes
```

### LLM wrapper interface

All LLM calls must go through one function in `backend/llm/`:

```python
def generate(prompt: str, system: str | None = None) -> str:
    """Call the configured LLM. Raises LLMError on failure."""
    ...
```

No other module may import the Gemini SDK directly. This keeps model-swapping to a single file change.

## 7. Build phases and acceptance criteria

| Phase | Deliverable | Done when |
|---|---|---|
| 1 | CLI script: URL → timestamped notes printed | Works on 3 videos; a video without captions fails with a clear message |
| 2 | Notes saved as markdown and pushed to GitHub | Re-running the same video overwrites the file and pushes; no duplicates in the repo |
| 3 | FastAPI endpoint `POST /process {video_id}` | Works from curl or a test script; runs classify → full pipeline |
| 3b | FastAPI launcher script | `start.sh` / `start.bat` starts the backend with one command; logs are written to `backend.log` in the project root; tested on the current OS |
| 4 | Chrome extension (auto-trigger) | Loading an educational video fires the pipeline automatically without any click; badge shows ⏳ then ✅; popup displays the notes; loading an entertainment video shows ⏭️ |
| 5 | Calendar integration | Three educational videos on one day produce exactly one calendar event |
| 6 | Hardening | Error handling, rate/cost limits, logging, README |

Commit after each phase passes. Do not start the next phase until the current one's criteria are met and I have run it myself.

## 8. Constraints

- No API keys in the extension or in git. `.env` is in `.gitignore` from the first commit; provide `.env.example` (see §13).
- Process long videos in chunks so LLM context limits are never hit. Default chunk target: ~4 minutes. Maximum chunks per video: configurable via `MAX_CHUNKS_PER_VIDEO` in `.env` (default: 10).
- **Rate limit cap behavior:** If `MAX_CHUNKS_PER_VIDEO` is reached, process only the first N chunks and append this banner to the note file: `> ⚠️ Notes truncated after chunk N of M due to cost cap (MAX_CHUNKS_PER_VIDEO=N).` Never fail silently.
- Handle failures per step: no captions → clear error; LLM error → surface message + skip chunk gracefully; calendar API error → log and return the note link anyway.
- Notes and calendar data stay private to me. GitHub notes repo must be private. GitHub PAT lives in `.env` only.

## 9. Not in v1

- Audio capture or transcription fallback
- Spaced-repetition review events and quizzes
- Sites other than YouTube
- Multi-user support or deployment

## 10. Risks to watch

- YouTube page structure and the unofficial transcript route can change. Isolate that code.
- The LLM may include content the video never said. Timestamps exist so I can check.
- Chrome extension service workers shut down when idle. All pipeline work runs on the backend; the content script only sends the video ID.
- YouTube loads new videos without a full page refresh. The content script must detect URL changes via `yt-navigate-finish` event or `MutationObserver`.
- YouTube Data API has a daily quota (10,000 units/day; one `videos.list` call = 1 unit). Normal personal use will never hit this.
- The backend must be running before the browser fires the first request. If it is down, the extension badge shows `❌` and logs the error; it does not retry automatically in v1. The launcher script is the only supported start method in v1; OS-level auto-start is not required.

## 11. Decisions (all resolved)

| # | Question | Decision |
|---|---|---|
| 1 | Where do notes live long-term? | GitHub private notes repo. Path: `YYYY-MM/<video_id>.md`. Link: GitHub web URL. |
| 2 | Which LLM? | Gemini 1.5 Flash via API. |
| 3 | Chunk length? | ~4 minutes. Single chunk for videos shorter than 4 min. Split at nearest caption boundary, never mid-sentence. |
| 4 | How to classify educational vs entertainment? | YouTube Data API v3 `categoryId`. Categories 27 + 28 = educational; borderline categories also proceed. |
| 5 | How does the pipeline get triggered? | Automatically by the content script on every YouTube video load. No user click needed. |
| 6 | How does the backend run? | Cross-platform launcher script (`start.sh` / `start.bat`). User runs it once per session. OS-level auto-start deferred to Phase 6. |

## 12. Testing

- **Unit tests** (required before Phase 6):
  - `classify/`: verify categoryId mapping — known educational IDs → `educational`, known entertainment IDs → `entertainment`.
  - `llm/`: mock Gemini; verify prompt format and output parsing.
  - `transcript/`: chunker edge cases — short video (<4 min), long video, chunk exactly on boundary.
  - `notes/`: idempotency — saving the same video ID twice produces exactly one file.
  - `calendar/`: idempotency — patching an existing event vs. creating when none exists.
- **Integration test** (Phase 3+):
  - End-to-end CLI test using a known video ID with a fixed transcript fixture (no real network call). Assert that the output markdown matches a golden file.
- **Extension** (Phase 4):
  - Manual test checklist (no automated browser tests in v1): auto-trigger on page load, SPA navigation to a new video, badge state transitions, popup read-only display, backend-down badge state.

## 13. `.env.example`

```ini
# LLM
GEMINI_API_KEY=your-gemini-api-key-here

# YouTube Data API (for video classification)
YOUTUBE_API_KEY=your-youtube-data-api-key-here

# Google Calendar OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# GitHub notes repository
GITHUB_PAT=your-personal-access-token-here
GITHUB_NOTES_REPO=<username>/<private-notes-repo>

# Pipeline config
NOTES_LOCAL_DIR=./notes
MAX_CHUNKS_PER_VIDEO=10
CHUNK_TARGET_MINUTES=4
```
