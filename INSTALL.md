# Installation Guide

## Prerequisites

- **Python 3.10+**
- **Claude Code CLI** — installed and authenticated (`claude -p` must work)
- **Google OAuth credentials** (only for Drive sync mode)

## Quick Setup

```bash
# Clone and enter the project
cd Kindle-to-md

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the package
pip install -e .
```

Verify the installation:

```bash
kindle2md --help
```

## Google Drive Setup (Optional)

Only needed if you want to use `kindle2md drive-sync` to pull books from Drive.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. Enable the **Google Drive API**
4. Create **OAuth 2.0 credentials** (Desktop or Web app)
5. Download the credentials JSON and save it as `credentials.json` in the project root
6. If using a Web app type, make sure `http://localhost:8080/` is in your redirect URIs

On first run, a browser window will open for authentication. The token is cached in `token.json` for subsequent runs.

## Claude Code CLI

The pipeline uses `claude -p` (pipe mode) to call Claude. This uses your existing Claude subscription — no API key needed.

Make sure Claude Code is installed and working:

```bash
claude -p "Hello" --model haiku
```

If this returns a response, you're good to go.

## Optional: launchd Watcher (macOS)

A launchd plist is included for automatic processing of PDFs dropped into `inbox/`. This is **not installed by default**.

To activate:

```bash
# Edit the plist to set your correct paths
nano com.kindle2md.watcher.plist

# Install
cp com.kindle2md.watcher.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.kindle2md.watcher.plist
```

To uninstall:

```bash
launchctl unload ~/Library/LaunchAgents/com.kindle2md.watcher.plist
rm ~/Library/LaunchAgents/com.kindle2md.watcher.plist
```
