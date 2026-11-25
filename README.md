# Sonora

A lightweight, minimal command-line YouTube playlist audio player for Linux terminals.

Sonora registers YouTube playlists locally, then streams them as audio through MPV — no
downloads, no browser, no account needed for public playlists.

## How playback works

Sonora never passes temporary Googlevideo URLs to MPV. For each track it runs
yt-dlp in streaming mode and pipes the raw audio bytes into MPV's stdin:

```
yt-dlp -f bestaudio/best -o - <video-url>  |  mpv --no-video -
```

The two processes are started together and terminated together for every track,
so skipping tracks leaves no orphaned processes behind, and playback does not
break when YouTube's CDN rejects a re-used stream URL (HTTP 403).

yt-dlp is invoked with an explicit JavaScript challenge configuration — the
Deno runtime (`--js-runtimes deno`) and EJS remote components from GitHub
(`--remote-components ejs:github`) — so format extraction works with current
YouTube even when the installed yt-dlp ships without up-to-date EJS scripts.

## Requirements

- Python 3.10+
- [MPV](https://mpv.io/) — audio playback engine
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — YouTube metadata and audio extraction
- [Deno](https://deno.com) 2.3+ — JavaScript runtime yt-dlp needs to solve
  YouTube's signature challenges

On Ubuntu: `sudo apt install mpv yt-dlp` and install Deno from
[deno.com](https://deno.com). If yt-dlp was installed from a distro package
and extraction still fails, `pipx install 'yt-dlp[default]'` bundles the
EJS components locally.

## Installation

From the project root:

```bash
pip install .
```

This registers the `sonora` command. It can also run straight from the source tree with
`python -m sonora`.

## Usage

```bash
sonora add <playlist_url>    # register a YouTube playlist
sonora list                  # show registered playlists
sonora show <index> [--limit N]
sonora use <index>           # select the active playlist
sonora                        # play the active playlist from the start
sonora play <track_index>    # play from a specific track (0-based)
sonora remove <index>        # remove a registered playlist
sonora --no-color <command>  # force plain, uncolored output
```

Playlist and track indices are both zero-based. `sonora` and `sonora play <index>` are
the only commands that start playback; the rest manage the local library.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Space` | Pause / resume |
| `<` / `>` | Previous / next track |
| `←` / `→` | Seek backward / forward 5 seconds |
| `9` / `0` | Volume down / up (5% steps) |
| `m` | Mute / unmute |
| `q` | Quit |

`←` / `→` are the arrow keys in the cursor cluster (between the letter block
and the numpad). `<` and `>` are typed as `Shift + ,` and `Shift + .`.

Because audio arrives through a pipe, seeking is limited to the portion of
the stream MPV has already buffered. Sonora enables a large demuxer cache
(150 MiB forward, 64 MiB back), so short ±5 second seeks — and jumps within
several minutes of buffered audio — work normally; seeking to a position
far ahead of the buffer is not possible with piped input.

## Colors

Sonora uses a small, consistent palette (dim metadata, bold titles, green for
the active playlist and success messages, red for errors). Colors are
automatically disabled when the output is not a terminal, when the
`NO_COLOR` environment variable is set, or when `--no-color` is passed.

## Playback status

While playing, one status line is redrawn in place once per second:

```
playing | 01:23/03:45 | 3/12 | Track title
```

For piped streams some metadata may be unavailable until MPV has demuxed the
stream; unavailable values show as `--:--`.

## Troubleshooting

| Message | Cause / fix |
| --- | --- |
| `yt-dlp is not installed or not in PATH` | Install it: `pipx install yt-dlp` or `sudo apt install yt-dlp` |
| `yt-dlp could not find the Deno JavaScript runtime` | Install Deno 2.3+ from https://deno.com |
| `could not load EJS challenge components` | Install the bundled components: `pipx install 'yt-dlp[default]'`, or check access to github.com |
| `YouTube rejected the request (HTTP 403)` | Update yt-dlp: `pipx upgrade yt-dlp` |
| `could not reach YouTube` | Check your network connection |
| `mpv is not installed or not in PATH` | Install it: `sudo apt install mpv` |

## Storage

Playlists are stored in `~/.local/share/sonora/playlists.json`. Delete the file to reset
the library. Playback streams audio only; YouTube's terms of service and content
licensing apply.
