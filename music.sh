#!/bin/bash

PLAYLIST="https://www.youtube.com/playlist?list=PLkDCtgX4ifwfI1NsCXPrqNdVXsiZSkh2X"

# Colors
RESET='\033[0m'
BOLD='\033[1m'
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
BLUE='\033[34m'
GRAY='\033[90m'
WHITE='\033[97m'
RED='\033[31m'

show_help() {
    cat <<'EOF'
music CLI

Usage:
  music
      Play the playlist from the beginning.

  music start <index>
      Start the playlist from the specified index.
      Playlist index starts at 0.

  music -l
  music --list
      List all tracks in the playlist.

Options:
  -l, --list
      List all tracks in the playlist.

  -h, --help
      Show this help message.

Keyboard shortcuts:
  Space       Pause / resume
  <           Previous track
  >           Next track
  Left        Seek backward 5 seconds
  Right       Seek forward 5 seconds
  9           Volume down
  0           Volume up
  m           Mute / unmute
  q           Quit
EOF
}

error() {
    printf "${RED}Error:${RESET} %s\n" "$1" >&2
    exit 1
}

list_tracks() {
    command -v yt-dlp >/dev/null 2>&1 ||
        error "yt-dlp is not installed or not in PATH."

    mapfile -t TRACKS < <(
        yt-dlp \
            --flat-playlist \
            --print '%(title)s' \
            --no-warnings \
            "$PLAYLIST" 2>/dev/null
    )

    [[ ${#TRACKS[@]} -gt 0 ]] ||
        error "playlist is empty or unavailable."

    printf "\n"
    printf "${BOLD}${CYAN}Playlist${RESET}\n"
    printf "${GRAY}%s${RESET}\n\n" "$PLAYLIST"

    for ((i=0; i<${#TRACKS[@]}; i++)); do
        printf "${YELLOW}[%d]${RESET} %s\n" "$i" "${TRACKS[$i]}"
    done

    printf "\n"
    printf "${GREEN}Total tracks:${RESET} %d\n" "${#TRACKS[@]}"
}

case "$1" in
    "")
        INDEX=0
        ;;

    start)
        [[ -n "$2" ]] || error "missing playlist index."
        [[ "$2" =~ ^[0-9]+$ ]] ||
            error "index must be a non-negative integer."
        INDEX="$2"
        ;;

    -l|--list)
        list_tracks
        exit 0
        ;;

    -h|--help)
        show_help
        exit 0
        ;;

    *)
        error "unknown command '$1'. Run 'music --help' for usage."
        ;;
esac

command -v yt-dlp >/dev/null 2>&1 ||
    error "yt-dlp is not installed or not in PATH."

command -v mpv >/dev/null 2>&1 ||
    error "mpv is not installed or not in PATH."

mapfile -t TRACKS < <(
    yt-dlp \
        --flat-playlist \
        --print '%(id)s' \
        --no-warnings \
        "$PLAYLIST" 2>/dev/null
)

[[ ${#TRACKS[@]} -gt 0 ]] ||
    error "playlist is empty or unavailable."

INPUT_CONF=$(mktemp)
trap 'rm -f "$INPUT_CONF"' EXIT

cat > "$INPUT_CONF" <<'EOF'
# Playlist navigation
< quit 20
> quit 21

# Quit
q quit 10

# Playback controls
SPACE cycle pause
LEFT seek -5
RIGHT seek 5
9 add volume -5
0 add volume 5
m cycle mute
EOF

while (( INDEX >= 0 && INDEX < ${#TRACKS[@]} )); do
    ID="${TRACKS[$INDEX]}"
    URL="https://www.youtube.com/watch?v=$ID"

    IFS=$'\t' read -r TITLE DURATION < <(
        yt-dlp \
            --no-playlist \
            --skip-download \
            --print $'%(title)s\t%(duration_string)s' \
            --no-warnings \
            "$URL" 2>/dev/null
    )

    TITLE="${TITLE:-Unknown title}"
    DURATION="${DURATION:-Unknown duration}"

    printf '\n'
    printf "${BOLD}${CYAN}[%d]${RESET} ${WHITE}%s${RESET}\n" "$INDEX" "$TITLE"
    printf "${BLUE}URL:${RESET} ${GRAY}%s${RESET}\n" "$URL"
    printf "${YELLOW}Now Playing${RESET}\n"

    yt-dlp \
        --no-playlist \
        --no-warnings \
        --quiet \
        -f 18 \
        -o - \
        "$URL" 2>/dev/null |
mpv \
    --no-video \
    --msg-level=all=status,file=no,cplayer=error,ao=no \
    --input-terminal=yes \
    --input-conf="$INPUT_CONF" \
    --term-status-msg='${playback-time} / ${duration} (${percent-pos}%)' \
    -

    MPV_STATUS=$?

case "$MPV_STATUS" in
    10)
        # q
        printf "${GRAY}[*] Playback stopped.${RESET}\n"
        exit 0
        ;;

    20)
        # <
        ((INDEX--))

        if (( INDEX >= 0 )); then
            printf "${BLUE}[<] Previous track:${RESET} [%d]\n" "$INDEX"
        else
            printf "${YELLOW}[<] Already at the first track.${RESET}\n"
            INDEX=0
        fi
        ;;

    21)
        # >
        ((INDEX++))

        if (( INDEX < ${#TRACKS[@]} )); then
            printf "${BLUE}[>] Next track:${RESET} [%d]\n" "$INDEX"
        else
            printf "${GREEN}[*] Playlist finished.${RESET}\n"
        fi
        ;;

    0)
        # Track finished normally.
        ((INDEX++))
        ;;

    *)
        printf "${RED}[%d] Playback failed. Skipping.${RESET}\n" "$INDEX" >&2
        ((INDEX++))
        ;;
esac
done
