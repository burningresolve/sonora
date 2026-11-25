"""MPV playback: yt-dlp streaming pipeline, keyboard input, terminal state.

Architecture: for each track, yt-dlp streams raw audio bytes to stdout and
MPV consumes them from stdin (``yt-dlp ... -o - ... | mpv --no-video -``).
The two processes are started together and torn down together by a single
``Pipeline`` object, so no orphaned processes remain when a track is skipped
or playback quits. MPV still runs an IPC socket for control (pause, seek,
volume) and for reading playback properties (position, duration, pause,
volume) to draw the status line.

Duration caveat: for piped input MPV reports duration only when the stream
container carries a header (many do; some only report it once the full track
has been demuxed). The status line shows ``--:--`` whenever a property is
missing, and updates once values become available.
"""

import itertools
import json
import os
import shutil
import socket
import subprocess
import sys
import termios
import time
import tty
from select import select

from . import colors, youtube

SEEK_SECONDS = 5
VOLUME_STEP = 5
POLL_INTERVAL = 0.1
SOCKET_TIMEOUT = 2.0


class PlayerError(Exception):
    """Raised when MPV is missing or the playback pipeline cannot start."""


def _mpv_args(socket_path: str) -> list[str]:
    """Command line for the MPV side of the streaming pipeline.

    MPV disables its cache for piped stdin and, without a cache, silently
    ignores seek commands on a non-seekable stream — which made the arrow-key
    seeks do nothing. Forcing the demuxer cache on (with a generous
    back-buffer) makes seek work within the audio MPV has already buffered.
    """
    return [
        "mpv",
        "--no-video",
        "--really-quiet",
        "--idle=no",
        "--cache=yes",
        "--demuxer-max-bytes=150MiB",
        "--demuxer-max-back-bytes=64MiB",
        "-",
        f"--input-ipc-server={socket_path}",
    ]


def run(playlist: dict, start: int) -> None:
    """Play the playlist from `start` until the end or a quit key."""
    tracks = playlist["tracks"]
    index = start
    print(colors.accent(f"playing: {playlist['name']}"))

    with Terminal():
        while 0 <= index < len(tracks):
            track = tracks[index]
            try:
                with Pipeline(track["id"]) as pipe:
                    action = _run_track(pipe, track, playlist, index,
                                        len(tracks))
            except youtube.YouTubeError as exc:
                _report_stream_error(exc)
                index += 1
                continue
            except PlayerError as exc:
                print(f"\n{colors.error(f'error: {exc}')}")
                return

            if action == "quit":
                print(f"\n{colors.dim('stopped')}")
                return
            index += -1 if action == "prev" else 1
            index = max(0, index)

    print(colors.dim("end of playlist"))


def _report_stream_error(exc: youtube.YouTubeError) -> None:
    print(f"\n{colors.warn(f'skipping: {exc}')}")
    if exc.hint:
        print(colors.dim(f"  {exc.hint}"))


def _run_track(pipe: "Pipeline", track: dict, playlist: dict,
               index: int, total: int) -> str:
    """Handle keys for one track; return "next", "prev", or "quit"."""
    _draw(pipe, track, playlist, index, total)
    last_draw = 0.0

    while True:
        if pipe.finished():  # stream ended on its own -> advance
            return "next"
        now = time.monotonic()
        if now - last_draw >= 1.0:
            _draw(pipe, track, playlist, index, total)
            last_draw = now
        key = _read_key(timeout=POLL_INTERVAL)
        if key is None:
            continue
        if key == "q":
            return "quit"
        if key == " ":
            pipe.mpv.toggle_pause()
        elif key == "<":
            return "prev"
        elif key == ">":
            return "next"
        elif key == "left":
            pipe.mpv.seek(-SEEK_SECONDS)
        elif key == "right":
            pipe.mpv.seek(SEEK_SECONDS)
        elif key == "9":
            pipe.mpv.nudge_volume(-VOLUME_STEP)
        elif key == "0":
            pipe.mpv.nudge_volume(VOLUME_STEP)
        elif key == "m":
            pipe.mpv.toggle_mute()
        if key in (" ", "9", "0", "m", "left", "right"):
            _draw(pipe, track, playlist, index, total)
            last_draw = time.monotonic()


class Pipeline:
    """One yt-dlp -> MPV pair per track, started and stopped together.

    yt-dlp writes audio bytes to stdout (its stdout is the pipe to MPV);
    MPV reads from stdin and exposes a JSON IPC socket for control. Closing
    tears both down in the right order: MPV first (it is the consumer), so
    yt-dlp's remaining writes hit a closed pipe and it exits instead of
    lingering; then yt-dlp if still running, then the socket file. Broken
    pipes between the two surface as a nonzero exit on either side,
    detected by `finished()` and the key loop.
    """

    _ids = itertools.count(1)

    def __init__(self, video_id: str):
        if shutil.which("mpv") is None:
            raise PlayerError("mpv is not installed or not in PATH")
        self.ytdlp = youtube.start_stream(video_id)
        self.mpv = Mpv(stdin=self.ytdlp.stdout)

    def finished(self) -> bool:
        """True once MPV has exited (track played through or failed).

        Only MPV's exit marks the track as done: yt-dlp may finish
        downloading (or fail) while MPV still plays buffered audio, and
        stopping then would cut the track short. A yt-dlp failure surfaces
        as MPV hitting EOF and exiting in turn; that exit is what we wait
        for.
        """
        return not self.mpv.alive()

    def close(self) -> None:
        # Order matters: stop MPV (the reader) so yt-dlp's remaining writes
        # hit a closed pipe and it exits instead of lingering.
        self.mpv.close()
        if self.ytdlp.poll() is None:
            self.ytdlp.terminate()
            try:
                self.ytdlp.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.ytdlp.kill()
                self.ytdlp.wait()
        self.ytdlp.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class Mpv:
    """MPV consuming piped audio from stdin, controlled via JSON IPC."""

    _ids = itertools.count(1000)

    def __init__(self, stdin):
        self._socket = f"/tmp/sonora-{os.getpid()}-{next(Mpv._ids)}.sock"
        self._proc = subprocess.Popen(
            _mpv_args(self._socket),
            stdin=stdin, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._sock = self._connect()

    def _connect(self):
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                break
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(SOCKET_TIMEOUT)
                sock.connect(self._socket)
                self._reader = sock.makefile("r")
                return sock
            except OSError:
                time.sleep(0.1)
        raise PlayerError("mpv failed to start or open its control socket")

    def _request(self, command: list):
        request_id = next(Mpv._ids)
        payload = {"command": command, "request_id": request_id}
        try:
            self._sock.sendall(json.dumps(payload).encode() + b"\n")
            for line in self._reader:
                reply = json.loads(line)
                if reply.get("request_id") == request_id:
                    if reply.get("error") != "success":
                        return None
                    return reply.get("data")
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def alive(self) -> bool:
        return self._proc.poll() is None

    def toggle_pause(self) -> None:
        self._request(["cycle", "pause"])

    def seek(self, seconds: float) -> None:
        self._request(["seek", seconds, "relative"])

    def nudge_volume(self, delta: int) -> None:
        current = self.get_property("volume")
        if current is None:
            return
        self.set_property("volume", max(0, min(100, current + delta)))

    def toggle_mute(self) -> None:
        self._request(["cycle", "mute"])

    def get_property(self, name: str):
        return self._request(["get_property", name])

    def set_property(self, name: str, value) -> None:
        self._request(["set_property", name, value])

    def close(self) -> None:
        if self._sock:
            self._reader.close()
            self._sock.close()
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
        try:
            os.unlink(self._socket)
        except OSError:
            pass


class Terminal:
    """Raw terminal mode with settings and cursor restored on exit.

    Used as a context manager around the whole playlist loop, so an
    exception or Ctrl-C during playback still restores the terminal before
    the error surfaces.
    """

    def __enter__(self):
        self._saved = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, *exc):
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._saved)
        print("\x1b[?25h", end="", flush=True)
        return False


_key_buf = b""


def _read_key(timeout: float) -> str | None:
    """Read one keypress; map arrow escape sequences to left/right.

    Reads raw bytes from the file descriptor instead of `sys.stdin`:
    Python's buffered text layer would swallow the whole arrow-key escape
    sequence on the first read(1) and leave the follow-up `select()` empty,
    so arrow keys would never register. The pending buffer keeps any bytes
    read past the key being decoded for the next call.
    """
    global _key_buf
    if not _key_buf:
        if not select([sys.stdin], [], [], timeout)[0]:
            return None
        _key_buf = os.read(sys.stdin.fileno(), 256)
        if not _key_buf:  # EOF
            return None
    byte = _key_buf[:1]
    _key_buf = _key_buf[1:]
    if byte == b"\x1b":
        if not _key_buf and select([sys.stdin], [], [], 0.05)[0]:
            _key_buf = os.read(sys.stdin.fileno(), 256)
        if _key_buf.startswith(b"["):
            _key_buf = _key_buf[1:]
            if _key_buf:
                code, _key_buf = _key_buf[:1], _key_buf[1:]
                return {"D": "left", "C": "right"}.get(code.decode())
        return None
    return byte.decode("utf-8", errors="replace")


def _format_time(seconds) -> str:
    if seconds is None:
        return "--:--"
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def _draw(pipe: Pipeline, track: dict, playlist: dict,
          index: int, total: int) -> None:
    """Redraw the single-line status display.

    Properties may be unavailable for piped streams (see module docstring);
    each is fetched independently and falls back to a placeholder, so the
    line stays readable while MPV demuxes the stream. The line is redrawn in
    place (carriage return + clear-to-end-of-line) once per second and on
    control-key presses; nothing else is written, which keeps flicker off.
    """
    mpv = pipe.mpv
    paused = bool(mpv.get_property("pause"))
    muted = bool(mpv.get_property("mute"))
    volume = mpv.get_property("volume")
    position = _format_time(mpv.get_property("time-pos"))
    duration = _format_time(mpv.get_property("duration"))
    state = colors.warn("paused") if paused else colors.success("playing")
    vol = "muted" if muted else f"{round(volume)}%" if volume is not None else "--"
    line = (
        f"\r\x1b[K{state} | {colors.dim(position)}/{colors.dim(duration)} | "
        f"{colors.dim(f'{index + 1}/{total}')} | "
        f"{colors.bold(track['title'][:45])} | "
        f"{colors.dim(track.get('channel', '')[:25])} | "
        f"{colors.accent(playlist['name'][:25])} | {colors.dim(f'vol {vol}')}"
    )
    print(line, end="", flush=True)
