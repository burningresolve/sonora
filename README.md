# music

A lightweight command-line music player for playing a YouTube playlist directly from the terminal.

The `music` CLI uses `yt-dlp` to retrieve playlist information and stream tracks to `mpv` for playback.

## Features

* Play a playlist directly from the terminal.
* Start playback from a specific track.
* List all tracks in the playlist.
* Navigate between tracks.
* Pause and resume playback.
* Seek forward and backward.
* Adjust volume.
* Mute and unmute audio.
* Continue automatically to the next track.

## Requirements

The following tools must be installed and available in your `PATH`:

* Bash
* `yt-dlp`
* `mpv`

## Installation

Clone the repository:

```bash
git clone https://github.com/burningresolve/music-cli.git
cd music-cli
```

Make the script executable:

```bash
chmod +x music
```

Optionally, make it available as a global command:

```bash
mkdir -p ~/.local/bin
ln -s "$(pwd)/music" ~/.local/bin/music
```

Make sure `~/.local/bin` is included in your `PATH`.

## Usage

### Play the playlist

Start playback from the first track:

```bash
./music
```

If installed as a global command:

```bash
music
```

### Start from a specific track

Playlist indexes start at `0`.

```bash
./music start 5
```

This starts playback from track index `5`.

### List tracks

Display all tracks in the playlist:

```bash
./music --list
```

or:

```bash
./music -l
```

### Show help

```bash
./music --help
```

or:

```bash
./music -h
```

## Playback Controls

| Key     | Action                  |
| ------- | ----------------------- |
| `Space` | Pause / resume          |
| `<`     | Previous track          |
| `>`     | Next track              |
| `Left`  | Seek backward 5 seconds |
| `Right` | Seek forward 5 seconds  |
| `9`     | Decrease volume         |
| `0`     | Increase volume         |
| `m`     | Mute / unmute           |
| `q`     | Quit                    |

## Configuration

The playlist URL is configured directly in the script:

```bash
PLAYLIST="https://www.youtube.com/playlist?list=..."
```

Replace the URL with your own YouTube playlist if needed.

## How It Works

```text
YouTube Playlist
       │
       ▼
     yt-dlp
       │
       ▼
  Track information
       │
       ▼
     yt-dlp
       │
       ▼
      mpv
       │
       ▼
    Playback
```

The script retrieves playlist and track information with `yt-dlp` and streams the selected track to `mpv` for audio playback.

## Notes

* An active internet connection is required.
* Playlist availability depends on the source platform and its access restrictions.
* The tool does not permanently download tracks.
