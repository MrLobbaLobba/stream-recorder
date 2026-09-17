## Context

The repository currently implements stream recording tailored to Fansly's REST API schema and headers in `fansly-recorder.py` and `config.py`. See `proposal.md` for motivation. To support Joystick.tv, we introduce a modular recording workflow that interacts with Joystick.tv channel endpoints while reusing the existing FFmpeg recording, conversion, contact sheet, and Discord alerting pipelines.

## Goals / Non-Goals

**Goals:**
- Implement `joystick-recorder.py` (or modular platform driver) to query Joystick.tv channel status.
- Retrieve the stream playback manifest URL (`.m3u8`) when a channel is live.
- Seamlessly pass the playback URL to FFmpeg for live transport stream recording.
- Re-use the existing post-processing pipeline: MP4 conversion, `mt` contact sheet generation, `rclone` cloud upload, and Discord webhook alerts.
- Keep the existing `fansly-recorder.py` operational so both platforms can be recorded independently.

**Non-Goals:**
- Bypassing paywalled / subscriber-only video encryption if the user does not supply valid session credentials.
- Rewriting the CLI/GUI into a web application.

## Decisions

### 1. Platform Isolation via Dedicated Script / Driver
- **Decision**: Create `joystick-recorder.py` alongside `fansly-recorder.py`, while sharing core utility functions (conversion, contact sheet, upload, notifications) or separating them into clean helper modules (`recorder_utils.py`).
- **Rationale**: Keeps Fansly recorder stable and avoids breaking existing setups or tmux configurations, while providing a clean entry point for Joystick.tv.
- **Alternatives considered**: Merging everything into a single CLI with a `--platform` flag. While unified, separating or abstracting allows running distinct `mprocs` processes easily (`python joystick-recorder.py <user>`).

### 2. HTTP Client & Cloudflare Session Handling
- **Decision**: Use `aiohttp` with standard browser headers and session cookies as default; support `curl_cffi` / `requests` fallback for environments where Cloudflare TLS fingerprint verification is active.
- **Rationale**: Direct `aiohttp` requests with valid session headers work for standard API endpoints, while fallback support prevents 403 blocks.
- **Alternatives considered**: Heavy headless browser automation (Playwright/Selenium). Avoided due to high resource overhead for 24/7 background polling loops.

### 3. Stream Recording & Post-Processing Pipeline
- **Decision**: Preserve standard FFmpeg flags (`-c copy`, `-reconnect 300`, `-movflags use_metadata_tags`) for stream dump to `.ts` and subsequent MP4 remuxing.
- **Rationale**: HLS manifests from Joystick.tv are standard TS/fMP4 chunks that FFmpeg captures reliably with low CPU overhead.

## Risks / Trade-offs

- **[Risk] Cloudflare Bot Protection on Joystick.tv API / Web**:
  - *Mitigation*: Provide configurable `headers` and `cookies` in `config.py` where users can paste their browser session cookies (similar to how Fansly authorization token is configured).
- **[Risk] Dynamic Playback Manifest Tokens**:
  - *Mitigation*: Re-fetch the live playback manifest directly upon detecting the stream start event rather than caching URLs across polling loops.
- **[Risk] API Schema Changes**:
  - *Mitigation*: Keep extraction logic isolated and well-logged to quickly diagnose response schema modifications.
