#!/usr/bin/env bash
# Posa channel archiver — full-fidelity local backup of @MatthewPosa uploads.
#
# Idempotent: yt-dlp's --download-archive records completed IDs, so re-runs
# only fetch videos not yet archived. Designed to run on Factotum via the
# posa-archive systemd service/timer (monthly, after update_catalog.py), or
# manually. The initial backfill is ~480h of video (roughly 1.5-3 TB).
#
# Layout: one directory per video containing the media file, info.json
# (full metadata), thumbnail, and any subtitle tracks (manual + ASR) —
# the subtitle sidecars double as the transcript corpus for the wiki.
set -u

CHANNEL_URL="https://www.youtube.com/@MatthewPosa/videos"
DEST="/mnt/media6t/archive/posa"
YTDLP="/srv/posa-wiki/venv/bin/yt-dlp"
LOG="$DEST/archive.log"

if ! mountpoint -q /mnt/media6t; then
    echo "FATAL: /mnt/media6t is not mounted; refusing to fill the SD card." >&2
    exit 1
fi
mkdir -p "$DEST"

echo "=== archive run started $(date -Is) ===" >> "$LOG"

nice -n 15 ionice -c 3 "$YTDLP" \
    --download-archive "$DEST/.archive.txt" \
    --format 'bv*+ba/b' \
    --merge-output-format mkv \
    --write-info-json \
    --write-thumbnail \
    --write-subs --write-auto-subs --sub-langs 'en.*' \
    --limit-rate 12M \
    --sleep-requests 0.75 \
    --retries 10 \
    --ignore-errors \
    --no-overwrites \
    --output "$DEST/%(upload_date)s - %(title).150B [%(id)s]/%(title).150B [%(id)s].%(ext)s" \
    "$CHANNEL_URL" >> "$LOG" 2>&1

STATUS=$?
COUNT=$(wc -l < "$DEST/.archive.txt" 2>/dev/null || echo 0)
echo "=== archive run finished $(date -Is) exit=$STATUS archived_total=$COUNT ===" >> "$LOG"
exit $STATUS
