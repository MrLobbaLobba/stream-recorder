## 1. Configuration & Dependencies

- [x] 1.1 Update `config.py` to add Joystick.tv settings (API endpoints, headers, cookies, and platform options)
- [x] 1.2 Update `requirements.txt` if additional HTTP/session packages (such as `curl_cffi` or `httpx`) are needed

## 2. Joystick.tv Recorder Implementation

- [x] 2.1 Implement `joystick-recorder.py` with channel status polling and metadata extraction (`getChannelData`, `getStreamData`)
- [x] 2.2 Implement live HLS manifest resolution and FFmpeg stream capture (`ffmpegSync`)
- [x] 2.3 Connect post-processing pipeline (`convertToMP4`, `generateContactSheet`, `uploadRecording`, and `sendWebhookLive`)

## 3. Process Management & Documentation

- [x] 3.1 Update `mprocs.yaml` and `start.sh` to include Joystick.tv streamer monitoring presets
- [x] 3.2 Update `README.md` with setup instructions, cookie/token extraction guide, and usage examples for Joystick.tv

## 4. Verification & Testing

- [x] 4.1 Validate channel polling logic against Joystick.tv usernames (offline check, error handling, live detection)
- [x] 4.2 Verify FFmpeg recording execution and webhook notifications
