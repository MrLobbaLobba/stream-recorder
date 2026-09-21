# Stream Recorder (Fansly & Joystick.tv)

An automated live stream monitoring and recording suite for **Fansly** and **Joystick.tv**. When a monitored streamer goes live, the script automatically captures video and audio streams, packages them into clean `.mp4` video files, and can optionally generate thumbnail contact sheets (`mt`), upload VODs to cloud storage (`rclone`), and post Discord webhook alerts.

Fully compatible with both **Linux** and **Windows**.

---

## Table of Contents
1. [Requirements](#1-requirements)
   * [Linux Setup](#linux-setup)
   * [Windows Setup](#windows-setup)
2. [Extracting Authentication Tokens](#2-extracting-authentication-tokens)
   * [Fansly Token](#how-to-find-your-fansly-token-fansly_token)
   * [Joystick.tv Credentials](#how-to-find-your-joysticktv-credentials-joystick_api_key--joystick_cookie_str)
   * [Creating the .env File (Linux & Windows)](#creating-the-env-file)
3. [Tracking Streamers & Storage Location](#3-tracking-streamers--storage-location)
   * [Running on Linux](#running-on-linux)
   * [Running on Windows](#running-on-windows)
   * [Where Recordings Are Saved](#where-recordings-are-saved)
4. [Compressing Recorded Videos with FFmpeg](#4-compressing-recorded-videos-with-ffmpeg)
   * [Single File Compression Recipes](#1-single-file-compression-recipes)
   * [Batch Compression on Linux](#2-batch-compression-on-linux-bash)
   * [Batch Compression on Windows (PowerShell & CMD)](#3-batch-compression-on-windows)
5. [Disclaimer & Project Vibe](#5-disclaimer--project-vibe)

---

## 1. Requirements

Before running the recorder, make sure your system meets the following requirements:

### System Prerequisites
* **Python 3.10 or higher**: [Download Python](https://www.python.org/downloads/) (must be added to system `PATH`).
* **FFmpeg**: [Download FFmpeg](https://ffmpeg.org/download.html). Must be accessible from your command line (`ffmpeg -version`). Required for stream capture, remuxing, and synchronization.
* *(Optional)* **rclone**: [Download rclone](https://rclone.org/downloads/). Needed only if you enable automatic cloud uploads in `config.py`.
* *(Optional)* **mt**: [Thumbnail Sheet Generator](https://github.com/mutschler/mt). Needed only if you enable automatic contact sheet creation.

---

### Linux Setup

1. **Install system packages** (Debian / Ubuntu / Mint / Pop!_OS):
   ```bash
   sudo apt update
   sudo apt install python3 python3-venv python3-pip ffmpeg tmux git curl -y
   ```
   *(On Arch Linux: `sudo pacman -S python ffmpeg tmux git curl`)*  
   *(On Fedora: `sudo dnf install python3 ffmpeg tmux git curl`)*

2. **Clone the repository**:
   ```bash
   git clone https://github.com/MrLobbaLobba/stream-recorder.git
   cd stream-recorder
   ```

3. **Create and activate the virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

### Windows Setup

1. **Install Python**:
   * Download the official installer from [python.org](https://www.python.org/downloads/).
   * ⚠ **Important**: Check the box **"Add python.exe to PATH"** before clicking Install.
   * *Alternatively via Windows Terminal / PowerShell*:
     ```powershell
     winget install Python.Python.3.12
     ```

2. **Install FFmpeg**:
   * The easiest way on Windows is using `winget` in PowerShell:
     ```powershell
     winget install Gyan.FFmpeg
     ```
   * *Alternatively via Chocolatey*: `choco install ffmpeg`
   * *Or manual installation*: Download the build from [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/), extract it, and add the `bin` folder (containing `ffmpeg.exe`) to your Windows User `PATH` environment variable.
   * Verify by opening a new PowerShell / Command Prompt and typing: `ffmpeg -version`.

3. **Clone the repository**:
   ```powershell
   git clone https://github.com/MrLobbaLobba/stream-recorder.git
   cd stream-recorder
   ```

4. **Create and activate the virtual environment**:
   * **PowerShell**:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
     *(If you see an execution policy error in PowerShell, run once: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`)*
   * **Command Prompt (CMD)**:
     ```cmd
     python -m venv .venv
     .venv\Scripts\activate.bat
     ```

5. **Install Python dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

---

## 2. Extracting Authentication Tokens

The recorder uses environment variables defined in a `.env` file to authenticate with Fansly and Joystick.tv.

### How to Find Your Fansly Token (`FANSLY_TOKEN`)
*(Works identically on Linux and Windows)*

1. Open [Fansly](https://fansly.com) in your web browser (Chrome, Edge, Firefox, Brave, etc.) and log into your account.
2. Open Developer Tools by pressing `F12` (or `Ctrl + Shift + I` / on macOS `Cmd + Option + I`).
3. Select the **Network** tab.
4. In the filter box, type `api` or `method:GET`.
5. Refresh the page (`F5`).
6. Click on any network request sent to `apiv3.fansly.com` (for example, `account?usernames=...` or `channel?...`).
7. In the panel on the right, under **Request Headers**, locate `authorization:`.
8. Copy the entire value (starts with letters and numbers such as `OTUwMDc5...`).

> **Alternative method**:
> In Developer Tools, go to the **Application** tab (Chrome / Edge) or **Storage** tab (Firefox). Expand **Local Storage** -> `https://fansly.com` -> click `session_active_session` and copy the token value.

---

### How to Find Your Joystick.tv Credentials (`JOYSTICK_API_KEY` & `JOYSTICK_COOKIE_STR`)
*(Works identically on Linux and Windows)*

Joystick.tv uses a combination of an API JWT token and browser cookies to authenticate and bypass Cloudflare:

1. Open [Joystick.tv](https://joystick.tv) in your browser and log into your account.
2. Open Developer Tools (`F12`).

#### A. Extracting `JOYSTICK_API_KEY`:
* Go to the **Application** tab (Chrome / Edge) or **Storage** tab (Firefox).
* Expand **Cookies** -> `https://joystick.tv`.
* Locate the cookie named `user`.
* The value is a URL-encoded JSON object. Inside it, look for `"token":"eyJhbGciOi..."`.
* That value starting with `eyJ...` is your JWT API token. Copy the entire token string.

#### B. Extracting `JOYSTICK_COOKIE_STR`:
* Go to the **Network** tab in Developer Tools.
* Refresh the page (`F5`).
* Click on the first document request (`joystick.tv` or any request to `joystick.tv/api/...`).
* In **Request Headers**, locate the header named `cookie:`.
* Right-click and copy the entire value of the `cookie` header (including `cf_clearance=...`, `application=...`, `user=...`, etc.).

---

### Creating the .env File

Create your local `.env` from the provided template:

* **On Linux / macOS**:
  ```bash
  cp .env.example .env
  ```
* **On Windows (PowerShell)**:
  ```powershell
  Copy-Item .env.example .env
  ```
* **On Windows (Command Prompt)**:
  ```cmd
  copy .env.example .env
  ```

Open `.env` in any text editor and paste your credentials:
```dotenv
# Fansly Authentication
FANSLY_TOKEN="OTUwMDc5..."

# Joystick.tv Authentication
JOYSTICK_API_KEY="eyJhbGciOi..."
JOYSTICK_COOKIE_STR="cf_clearance=...; application=...; user=..."
```

---

### Browser-Independent Credential Diagnostics & Renewal (`check-tokens.py`)

You can verify whether your session cookies, Cloudflare clearances, and streaming keys are valid or expired in ~1 second without launching or depending on any web browser:

```bash
# Run diagnostics on all configured credentials:
python3 check-tokens.py
```

Sample output:
```text
=================================================================
       CREDENTIAL DIAGNOSTICS (BROWSER-INDEPENDENT)
=================================================================
[✓] Fansly Token: Valid (Connected as @username, ID: ...)
[✓] Joystick Cookie (cf_clearance): Valid (HTTP 200 - Cloudflare clearance & site active)
[✓] Joystick Streaming Key: Valid JWT token (User: username, ID: ...), Issued: ...
=================================================================
```

#### Updating & Renewing Credentials Directly into `.env`:
You can update expired tokens or cookies automatically without opening or manually editing files:

* **Interactive CLI Menu**:
  ```bash
  python3 check-tokens.py --renew
  ```
  Presents an interactive menu, asks you to paste the new token or cookie, writes it safely into `.env`, and immediately re-validates the connection.

* **Direct One-Line Commands**:
  ```bash
  # Update Joystick Cookie (Cloudflare cf_clearance & session):
  python3 check-tokens.py --set-joystick-cookie "cf_clearance=...; user=..."

  # Update Joystick Streaming Key (JWT Token):
  python3 check-tokens.py --set-joystick-key "eyJhbGciOi..."

  # Update Fansly Token:
  python3 check-tokens.py --set-fansly "your_new_fansly_token"
  ```

---

### Tracking Status & In-Console Credential Warnings

The recorders monitor streamers silently in the background without intrusive desktop notifications or popups. Status and credential warnings are displayed directly inline in the console output while tracking:

* **Joystick.tv Public Fallback**: If `JOYSTICK_COOKIE_STR` expires or encounters a Cloudflare challenge, the recorder seamlessly falls back to unauthenticated public fetching so you never miss a broadcast, logging:
  ```text
  [info] <streamer> is offline (cookie expired, public fallback active), checking again in 120s
  ```
* **Fansly Token Status**: If `FANSLY_TOKEN` expires (HTTP 401), the monitor logs:
  ```text
  [info] <streamer> is offline (token expired: HTTP 401), checking again in 130s
  ```
* **Diagnostic & Renewal Tool**: To check or renew any token or cookie at any time without a browser, run:
  ```bash
  python3 check-tokens.py
  python3 check-tokens.py --renew
  ```

---

## 3. Tracking Streamers & Storage Location

### Running on Linux

#### Option A: Background Execution with `tmux` (Recommended)
Launch streamers in decoupled background sessions using [`start.sh`](start.sh):
```bash
# Track Joystick.tv streamer
./start.sh <username> joystick

# Track Fansly streamer
./start.sh <username> fansly
```
* Each streamer runs in its own session (`<username>-joystick` or `<username>-fansly`).
* If `tmux` is not installed, it automatically falls back to running in the background via `nohup` and creates `<username>-<platform>.log`.

#### Option B: Multi-Streamer Monitoring via `captures/list`
To track multiple streamers across both platforms at the same time:
1. Edit [`captures/list`](captures/list):
   ```bash
   sh start.sh <username1> joystick
   sh start.sh <username2> fansly
   sh start.sh <username3> fansly
   ```
2. Run the list script:
   ```bash
   sh captures/list
   ```

#### Helpful Linux `tmux` Commands:
* **List active sessions**: `tmux ls`
* **Attach to live console**: `tmux attach -t <username>-<platform>` (e.g. `tmux attach -t <username>-joystick`)
* **Detach without closing**: Press `Ctrl + B`, release both keys, then press `D`.
* **Stop a streamer session**: `tmux kill-session -t <username>-<platform>`

#### Option C: Direct Console Execution
```bash
python joystick-recorder.py <username>
python fansly-recorder.py <username>
```

---

### Running on Windows

#### Option A: Built-in Batch Shortcuts
The repository includes Windows command launchers. From your terminal (CMD or PowerShell):
```cmd
# Track on Joystick.tv
joystick <username>

# Track on Fansly
fansly <username>
```
*(These invoke `joystick.cmd` and `fansly.cmd` respectively).*

#### Option B: Direct Python Execution
With your virtual environment active:
```powershell
# Joystick.tv
python joystick-recorder.py <username>

# Fansly
python fansly-recorder.py <username>
```

#### Option C: Multi-Streamer Monitoring on Windows

1. **Using Separate PowerShell Windows**:
   Launch multiple background windows that stay open and monitor continuously:
   ```powershell
   Start-Process python -ArgumentList "joystick-recorder.py <username1>"
   Start-Process python -ArgumentList "fansly-recorder.py <username2>"
   Start-Process python -ArgumentList "fansly-recorder.py <username3>"
   ```

2. **Using `mprocs` (Terminal Multiplexer for Windows & Linux)**:
   * Install `mprocs`: `winget install mprocs` or `choco install mprocs`
   * Edit [`mprocs.yaml`](mprocs.yaml) with your desired streamers:
     ```yaml
     procs:
       streamer_one:
         shell: "python joystick-recorder.py <username1>"
       streamer_two:
         shell: "python fansly-recorder.py <username2>"
     ```
   * Run `mprocs` to monitor all streamers side-by-side in one window.

3. **Using WSL / WSL2**:
   If you have the Windows Subsystem for Linux (WSL) installed, you can use the Linux setup directly with `tmux` and `sh captures/list`.

---

### Where Recordings Are Saved

All recordings and media files are stored organized by streamer username:

* **On Linux**: `captures/<streamer_username>/`
* **On Windows**: `captures\<streamer_username>\`

```
captures/
└── <streamer_username>/
    ├── .<username>_YYYYMMDD_HHMMSS_v<id>_vtmp.mp4   # Temporary live video track
    ├── .<username>_YYYYMMDD_HHMMSS_v<id>_atmp.mp4   # Temporary live audio track
    └── <username>_YYYYMMDD_HHMMSS_v<id>.mp4         # Finalized synchronized MP4
```

* **Live In-Progress**: While recording from Joystick.tv, temporary video (`_vtmp.mp4`) and audio (`_atmp.mp4`) streams are fetched concurrently.
* **Finalizing**: When the stream concludes or goes offline, FFmpeg muxes the tracks into a final `<username>_YYYYMMDD_HHMMSS_v<id>.mp4` file and cleans up the temporary files.
* On Fansly, streams are captured into `.ts` format and remuxed directly into `.mp4`.

---

## 4. Compressing Recorded Videos with FFmpeg

Live streams recorded at source quality (1080p 60fps) can take **1.5 GB to 3.0 GB per hour**. You can significantly reduce the file size after recording using FFmpeg.

### 1. Single File Compression Recipes
*(Commands run identically in Linux Bash, Windows PowerShell, and Windows CMD)*

#### High-Efficiency H.264 (Universal Compatibility)
Recommended for sharing, fast encoding, and compatibility with every media player:
```bash
ffmpeg -i input.mp4 -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k -movflags +faststart output_compressed.mp4
```
* `-crf 23`: Constant Rate Factor (18–22 is visually lossless; 23–26 is ideal for web video).
* `-preset medium`: Speed vs compression ratio (`fast`, `medium`, `slow`).
* `-movflags +faststart`: Moves metadata to the start of the file for instant streaming.

#### Maximum Space Saving with H.265 / HEVC (~40-50% smaller)
```bash
ffmpeg -i input.mp4 -c:v libx265 -crf 26 -preset medium -c:a aac -b:a 128k -tag:v hvc1 -movflags +faststart output_hevc.mp4
```
* `-crf 26`: In HEVC, CRF 26 is visually comparable to CRF 23 in H.264 while taking half the disk space.
* `-tag:v hvc1`: Ensures compatibility with modern players, browsers, and Apple devices.

#### GPU Hardware Acceleration (NVIDIA NVENC)
For systems with an NVIDIA graphics card (fast encoding for multi-hour VODs):
```bash
ffmpeg -i input.mp4 -c:v h264_nvenc -cq 24 -preset p4 -c:a aac -b:a 128k -movflags +faststart output_nvenc.mp4
```

---

### 2. Batch Compression on Linux (Bash)

To automatically compress all recorded `.mp4` files inside the `captures/` folder:

```bash
for file in captures/*/*.mp4; do
  # Skip temporary files or already compressed files
  case "$file" in
    *.*tmp.mp4|*_compressed.mp4) continue ;;
  esac
  
  echo "Compressing: $file"
  output="${file%.mp4}_compressed.mp4"
  ffmpeg -i "$file" -c:v libx264 -crf 23 -preset fast -c:a aac -b:a 128k -movflags +faststart "$output" && rm "$file"
done
```

---

### 3. Batch Compression on Windows

#### Using PowerShell:
```powershell
Get-ChildItem -Path "captures\*\*.mp4" -Exclude "*tmp.mp4","*_compressed.mp4" | ForEach-Object {
    Write-Host "Compressing: $($_.FullName)"
    $output = $_.FullName.Replace(".mp4", "_compressed.mp4")
    ffmpeg -i $_.FullName -c:v libx264 -crf 23 -preset fast -c:a aac -b:a 128k -movflags +faststart $output
    if ($LASTEXITCODE -eq 0) { Remove-Item $_.FullName }
}
```

#### Using Command Prompt (CMD):
```cmd
for /r "captures" %i in (*.mp4) do @if not "%~ni"=="*tmp" if not "%~ni"=="*_compressed" ffmpeg -i "%i" -c:v libx264 -crf 23 -preset fast -c:a aac -b:a 128k -movflags +faststart "%~dpni_compressed.mp4" && del "%i"
```

---

## 5. Disclaimer & Project Vibe

> [!NOTE]
> **Stream Resilience & `moov` Atom Handling**: Both recorders (`joystick-recorder.py` and `fansly-recorder.py`) are engineered to guarantee that recorded `.mp4` videos are always 100% playable and corruption-free. Live captures on Joystick utilize fragmented MP4 (`frag_keyframe+empty_moov+default_base_moof`) so that video and audio headers are valid and self-contained from the very first second. Furthermore, whenever you stop a recording (`Ctrl+C`, `SIGINT`, `SIGTERM`, or `SIGBREAK`), both scripts intercept the signal gracefully, cleanly flush FFmpeg streams, and automatically finalize the video with `-movflags +faststart`—placing the `moov` atom at the very beginning of the `.mp4` file for instantaneous playback and streaming in any media player or browser.
>
> This codebase was built and iterated through **vibecoding** ✨. While it may not feature enterprise-grade architecture or formal test suites, it is practical, battle-tested, and fully functional for amateur and hobbyist stream archivers looking to reliably record their favorite creators without hassle.

* Fansly is operated by Select Media LLC.
* This repository is an independent open-source utility and is not affiliated with, sponsored by, or endorsed by Select Media LLC, Fansly, or Joystick.tv.
* Users are solely responsible for adhering to each platform's Terms of Service and respecting creators' rights.
