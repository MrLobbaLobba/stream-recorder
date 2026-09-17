## Why

The current recorder only supports Fansly (`fansly-recorder.py`), querying Fansly-specific API endpoints (`apiv3.fansly.com`) and data structures. Adapting the project to support Joystick.tv allows users to automatically monitor Joystick.tv streamers, capture live HLS/m3u8 broadcasts via FFmpeg, generate thumbnail sheets, upload VODs using rclone, and receive Discord webhook alerts for Joystick.tv channels.

## What Changes

- Add a dedicated Joystick.tv stream recorder module (`joystick-recorder.py`) or unified multi-platform recorder interface.
- Add configuration settings in `config.py` (or a dedicated `config_joystick.py` / platform config section) for Joystick.tv headers, cookies, API endpoints, and platform-specific options.
- Implement live stream status probing and HLS stream extraction for Joystick.tv channels (`api.joystick.tv` / channel web manifests).
- Integrate Cloudflare/session-handling capabilities (e.g. `curl_cffi` or customizable session headers/cookies) to reliably query Joystick.tv endpoints.
- Update process management configs (`mprocs.yaml`, `start.sh`) and documentation (`README.md`) for Joystick.tv workflow.

## Capabilities

### New Capabilities
- `joystick-recorder`: Enables automated monitoring, live detection, stream capture, post-processing (contact sheet generation, cloud upload), and Discord webhook notification for Joystick.tv channels.

### Modified Capabilities
<!-- None: This is a brownfield addition of a new platform capability -->

## Impact

- **New files**: `joystick-recorder.py` (and/or modular platform adapters).
- **Modified files**: `config.py`, `requirements.txt` (if session handling packages like `curl_cffi` are needed), `mprocs.yaml`, `README.md`.
- **System dependencies**: `ffmpeg`, `rclone`, `mt` (reused as-is).
