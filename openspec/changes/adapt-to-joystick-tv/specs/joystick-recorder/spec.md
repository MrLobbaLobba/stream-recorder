## Purpose

Provides automated live stream monitoring, capture, post-processing, and alerting for creators on the Joystick.tv platform.

## ADDED Requirements

### Requirement: Monitor Channel Status
The system SHALL periodically query the status of a configured Joystick.tv username to determine whether the streamer is actively broadcasting live video.

#### Scenario: Streamer is offline
- **WHEN** the channel check runs and the streamer is not currently broadcasting
- **THEN** the system logs the offline status and waits for the configured check interval before polling again

#### Scenario: Streamer goes online
- **WHEN** the channel check detects an active live broadcast with an available playback stream URL
- **THEN** the system logs the online status, triggers live webhook notifications if enabled, and initiates recording

### Requirement: Record Live HLS Stream
The system SHALL capture the live stream into a media container file using FFmpeg with stream reconnection resilience.

#### Scenario: Active stream recording
- **WHEN** the stream playback manifest (.m3u8) is provided
- **THEN** FFmpeg records the stream segments to a timestamped file in the local captures directory until the broadcast ends

### Requirement: Post-Process and Convert Recording
The system SHALL convert the raw transport stream into an MP4 file upon completion of the live broadcast.

#### Scenario: Successful conversion
- **WHEN** stream recording finishes
- **THEN** the system converts the `.ts` file to `.mp4` and cleans up temporary `.ts` files if configured

### Requirement: Generate Thumbnail Contact Sheet
The system SHALL generate a contact sheet image summarizing key moments from the recorded video if thumbnail generation is enabled.

#### Scenario: Contact sheet generation
- **WHEN** an MP4 recording is ready and thumbnail generation is enabled
- **THEN** the system executes the contact sheet tool to output a `.jpg` overview of the video

### Requirement: Remote Cloud Upload
The system SHALL upload the final video and thumbnail assets to the configured cloud remote path using rclone.

#### Scenario: Upload after stream
- **WHEN** recording and conversion are complete and upload is enabled
- **THEN** the system transfers the MP4 and thumbnail files to the remote destination via rclone

### Requirement: Discord Webhook Notifications
The system SHALL send Discord embed messages announcing stream start, conversion completion, and cloud upload events.

#### Scenario: Live notification
- **WHEN** a channel comes online and webhooks are enabled
- **THEN** the system sends a live notification with streamer metadata to the designated Discord webhook URL
