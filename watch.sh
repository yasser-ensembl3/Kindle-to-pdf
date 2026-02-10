#!/bin/bash
# kindle2md watcher — triggered by launchd when new files appear in inbox/
# Usage: This script is called by com.kindle2md.watcher.plist

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INBOX="$SCRIPT_DIR/inbox"
PROCESSED="$INBOX/processed"
OUTPUT="$SCRIPT_DIR/output"
LOG="$SCRIPT_DIR/watch.log"

mkdir -p "$PROCESSED" "$OUTPUT"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

log "Watcher triggered — scanning inbox"

for pdf in "$INBOX"/*.pdf; do
    [ -f "$pdf" ] || continue

    filename=$(basename "$pdf")
    log "Processing: $filename"

    # Run the full pipeline
    kindle2md pipeline "$pdf" --output-dir "$OUTPUT" 2>> "$LOG"
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        log "Success: $filename"
        mv "$pdf" "$PROCESSED/$filename"
    else
        log "Failed (exit $exit_code): $filename"
    fi
done

log "Watcher scan complete"
