"""YouTube metadata retrieval and audio streaming via yt-dlp.

Streaming model: yt-dlp pipes raw audio bytes to stdout (``-o -``) which MPV
consumes from stdin. No temporary Googlevideo URLs are extracted or passed to
MPV directly, so playback is not affected by URL expiry, session binding, or
HTTP 403 responses on the CDN side.

JavaScript challenge solving: YouTube serves JavaScript challenges that yt-dlp
must execute to extract stream signatures. We explicitly enable the Deno
runtime (``--js-runtimes deno``) and allow EJS remote components from GitHub
(``--remote-components ejs:github``) so extraction works even when the
installed yt-dlp ships without current EJS scripts.
"""

import json
import shutil
import subprocess

YT_DLP = "yt-dlp"

# Shared yt-dlp arguments: explicit JS runtime + EJS remote components.
# Passing them on every invocation (instead of relying on the user's config)
# keeps Sonora's requirements self-contained and the behavior reproducible.
JS_RUNTIME_ARGS = [
    "--js-runtimes", "deno",
    "--remote-components", "ejs:github",
]

STREAM_ARGS = [
    "-f", "bestaudio/best",
    "-o", "-",           # stream media bytes to stdout
    "-q", "--no-progress",
]


class YouTubeError(Exception):
    """Base class; message text is shown to the user as-is."""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


class MissingDependencyError(YouTubeError):
    """A required external tool (yt-dlp, Deno) is not installed."""


class ExtractionError(YouTubeError):
    """yt-dlp could not extract stream formats or metadata for a video."""


class NetworkError(YouTubeError):
    """yt-dlp could not reach YouTube (connectivity, DNS, timeouts)."""


def _run(args: list[str]) -> subprocess.CompletedProcess:
    if shutil.which(YT_DLP) is None:
        raise MissingDependencyError(
            "yt-dlp is not installed or not in PATH",
            hint="install it with: pipx install yt-dlp  (or: sudo apt install yt-dlp)",
        )
    try:
        return subprocess.run([YT_DLP, *args, "--ignore-config"],
                              capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise NetworkError(
            "yt-dlp timed out while contacting YouTube",
            hint="check your network connection and try again",
        )


def _classify(proc: subprocess.CompletedProcess, context: str) -> YouTubeError:
    """Map a failed yt-dlp run to the most specific error we can report."""
    stderr = _read_stderr(proc).lower()
    if "sign in to confirm" in stderr or "cookies" in stderr:
        return ExtractionError(
            f"{context}: YouTube requires sign-in for this content",
            hint="this video is restricted; Sonora cannot play it",
        )
    if "deno" in stderr or "js runtime" in stderr or "javascript runtime" in stderr:
        return MissingDependencyError(
            f"{context}: yt-dlp could not find the Deno JavaScript runtime",
            hint="install Deno 2.3+ (https://deno.com) so yt-dlp can solve "
                "YouTube's JavaScript challenges",
        )
    if "remote component" in stderr or "ejs" in stderr:
        return ExtractionError(
            f"{context}: yt-dlp could not load EJS challenge components",
            hint="check network access to github.com, or install yt-dlp-ejs: "
                "pipx install 'yt-dlp[default]'",
        )
    if "http error 403" in stderr or "403 forbidden" in stderr:
        return ExtractionError(
            f"{context}: YouTube rejected the request (HTTP 403)",
            hint="update yt-dlp (pipx upgrade yt-dlp) and try again",
        )
    if any(token in stderr for token in
           ("urlopen error", "temporary failure in name resolution",
            "network", "connection", "timed out", "ssl")):
        return NetworkError(
            f"{context}: could not reach YouTube",
            hint="check your network connection and try again",
        )
    detail = _read_stderr(proc).splitlines()
    last = detail[-1] if detail else "unknown error"
    return ExtractionError(f"{context}: {last}")


def _read_stderr(proc: subprocess.CompletedProcess) -> str:
    return (proc.stderr or "").strip()


def playlist_id(url: str) -> str:
    """Extract the playlist ID from a YouTube playlist URL."""
    marker = "list="
    start = url.find(marker)
    if start == -1:
        raise YouTubeError(f"not a YouTube playlist URL: {url}")
    playlist = url[start + len(marker):].split("&")[0]
    if not playlist or playlist.startswith(("RD", "UL", "OL")):
        raise YouTubeError(f"not a regular YouTube playlist URL: {url}")
    return playlist


def fetch_playlist(url: str) -> dict:
    """Return {"id", "url", "name", "tracks": [{"id", "title", "channel"?}]}."""
    proc = _run(["--flat-playlist", "--dump-single-json", "--no-warnings", url])
    if proc.returncode != 0:
        raise _classify(proc, "could not read playlist")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ExtractionError("yt-dlp returned unreadable data for this playlist")
    if "entries" not in data:
        raise ExtractionError("this URL does not point to a playlist")

    tracks = []
    for entry in data["entries"]:
        if not entry or entry.get("_type") == "playlist":
            continue
        track = {"id": entry.get("id") or "",
                 "title": entry.get("title") or "[unavailable]"}
        channel = entry.get("channel") or entry.get("uploader")
        if channel:
            track["channel"] = channel
        tracks.append(track)

    return {"id": data.get("id") or playlist_id(url), "url": url,
            "name": data.get("title") or "Untitled playlist", "tracks": tracks}


def stream_args(video_url: str) -> list[str]:
    """Full argument list to stream one video's audio to stdout via yt-dlp."""
    return [*JS_RUNTIME_ARGS, *STREAM_ARGS, video_url]


def start_stream(video_id: str) -> subprocess.Popen:
    """Start yt-dlp streaming audio bytes to stdout for one YouTube video.

    The caller pipes the returned process's stdout into MPV's stdin. With
    ``-o -`` yt-dlp writes raw media bytes to stdout; logs go to stderr, so
    the pipe never mixes with them. No temporary Googlevideo URL is ever
    extracted, which is what previously caused HTTP 403 errors in MPV.
    """
    if not video_id:
        raise ExtractionError("no video id for this track")
    if shutil.which(YT_DLP) is None:
        raise MissingDependencyError(
            "yt-dlp is not installed or not in PATH",
            hint="install it with: pipx install yt-dlp  (or: sudo apt install yt-dlp)",
        )
    url = f"https://www.youtube.com/watch?v={video_id}"
    return subprocess.Popen(
        [YT_DLP, *stream_args(url), "--ignore-config"],
        stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
