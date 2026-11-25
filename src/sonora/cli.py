"""Command-line interface: argument parsing and command dispatch."""

import argparse
import sys

from . import __version__, colors, playlist as store, player, youtube


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="sonora",
        description="A lightweight command-line YouTube playlist audio player.",
    )
    parser.add_argument("-v", "--version", action="version",
                        version=__version__)
    parser.add_argument("--no-color", action="store_true", default=None,
                        help="disable colored output even on a color terminal")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    add_cmd = sub.add_parser("add", help="register a YouTube playlist")
    add_cmd.add_argument("url", help="YouTube playlist URL")

    sub.add_parser("list", help="show registered playlists")

    show_cmd = sub.add_parser("show", help="show a playlist's tracks")
    show_cmd.add_argument("index", type=int, help="playlist index (0-based)")
    show_cmd.add_argument("--limit", type=int, default=None,
                          help="number of tracks to display")

    use_cmd = sub.add_parser("use", help="select the active playlist")
    use_cmd.add_argument("index", type=int, help="playlist index (0-based)")

    remove_cmd = sub.add_parser("remove", help="remove a registered playlist")
    remove_cmd.add_argument("index", type=int, help="playlist index (0-based)")

    play_cmd = sub.add_parser("play", help="play the active playlist from a track")
    play_cmd.add_argument("track_index", type=int, help="track index (0-based)")

    args = parser.parse_args(argv)
    colors.configure(no_color=args.no_color)

    try:
        return _dispatch(args)
    except youtube.YouTubeError as exc:
        return _fail(str(exc), getattr(exc, "hint", None))
    except (store.PlaylistError, player.PlayerError) as exc:
        return _fail(str(exc))
    except KeyboardInterrupt:
        print()
        return 130


def _fail(message: str, hint: str | None = None) -> int:
    print(colors.error(f"error: {message}"), file=sys.stderr)
    if hint:
        print(colors.dim(f"  hint: {hint}"), file=sys.stderr)
    return 1


def _dispatch(args) -> int:
    if args.command is None:
        return _cmd_play_default()

    if args.command == "add":
        return _cmd_add(args.url)
    if args.command == "list":
        return _cmd_list()
    if args.command == "show":
        return _cmd_show(args.index, args.limit)
    if args.command == "use":
        return _cmd_use(args.index)
    if args.command == "remove":
        return _cmd_remove(args.index)
    if args.command == "play":
        return _cmd_play(args.track_index)
    return _cmd_play_default()


def _cmd_add(url: str) -> int:
    data = youtube.fetch_playlist(url)
    registry = store.load()
    if not store.add(registry, data):
        print(colors.dim(f"playlist already registered: {data['name']}"))
        return 0
    count = len(data["tracks"])
    print(colors.success(
        f"added: {data['name']} ({count} track{'s' if count != 1 else ''})"))
    return 0


def _cmd_list() -> int:
    registry = store.load()
    playlists = registry["playlists"]
    if not playlists:
        print(colors.dim("no playlists registered — add one with: sonora add <url>"))
        return 0
    for i, p in enumerate(playlists):
        is_active = registry["active"] == i
        marker = colors.active("*") if is_active else colors.dim(" ")
        name = colors.bold(p["name"]) if is_active else p["name"]
        count = colors.dim(f"({len(p['tracks'])} tracks)")
        print(f"{marker} {colors.dim(str(i))}  {name}  {count}")
    return 0


def _cmd_show(index: int, limit: int | None) -> int:
    registry = store.load()
    playlists = registry["playlists"]
    if index < 0 or index >= len(playlists):
        return _fail(f"invalid playlist index: {index}")
    playlist = playlists[index]
    tracks = playlist["tracks"]
    if not tracks:
        print(colors.dim(f"{playlist['name']}: empty playlist"))
        return 0
    shown = tracks if limit is None else tracks[:max(0, limit)]
    print(f"{colors.accent(playlist['name'])} — "
          f"{colors.dim(f'{len(tracks)} tracks')}")
    for i, t in enumerate(shown):
        channel = f" — {colors.dim(t['channel'])}" if t.get("channel") else ""
        print(f"{colors.dim(f'{i:>4}')}  {colors.bold(t['title'])}{channel}")
    if limit is not None and limit < len(tracks):
        print(colors.dim(f"      ... and {len(tracks) - limit} more "
                         f"(raise --limit to view)"))
    return 0


def _cmd_use(index: int) -> int:
    registry = store.load()
    playlists = registry["playlists"]
    previous = registry.get("active")
    if index < 0 or index >= len(playlists):
        return _fail(f"invalid playlist index: {index}")
    selected = store.use(registry, index)
    if previous is not None and previous != index:
        print(colors.dim(f"was:  {playlists[previous]['name']}"))
    print(colors.success(f"now:  {selected['name']}"))
    return 0


def _cmd_remove(index: int) -> int:
    registry = store.load()
    try:
        removed = store.remove(registry, index)
    except store.PlaylistError as exc:
        return _fail(str(exc))
    print(colors.success(f"removed: {removed['name']}"))
    if registry["active"] is None and registry["playlists"]:
        print(colors.dim("active playlist cleared; use: sonora use <index>"))
    elif not registry["playlists"]:
        print(colors.dim("no playlists left"))
    return 0


def _resolve_active(registry) -> dict | None:
    active = store.active_playlist(registry)
    if active is not None:
        return active
    if registry["playlists"]:
        selected = store.use(registry, 0)
        print(colors.dim(f"auto-selected playlist: {selected['name']}"))
        return selected
    return None


def _cmd_play_default() -> int:
    registry = store.load()
    active = _resolve_active(registry)
    if active is None:
        print(colors.dim("no playlists registered — add one with: sonora add <url>"))
        return 1
    player.run(active, 0)
    return 0


def _cmd_play(track_index: int) -> int:
    registry = store.load()
    active = _resolve_active(registry)
    if active is None:
        print(colors.dim("no playlists registered — add one with: sonora add <url>"))
        return 1
    tracks = active["tracks"]
    if not tracks:
        return _fail(f"playlist {active['name']} is empty")
    if track_index < 0 or track_index >= len(tracks):
        return _fail(f"invalid track index: {track_index}")
    player.run(active, track_index)
    return 0
