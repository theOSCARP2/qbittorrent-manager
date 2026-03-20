# qBittorrent Manager

A lightweight Flask web interface to manage a remote qBittorrent instance.

> 🇫🇷 [Version française](README.md)

## Features

- **Torrent list** — paginated, sortable and searchable table (server-side DataTables)
- **Torrent actions** — pause, resume, recheck, delete (with or without files)
- **Tracker view** — list of all trackers across all torrents with OK/error/pending status
- **Bulk tracker operations** — add, replace or remove a tracker URL across all torrents
- **Background cache** — torrent list is cached and automatically refreshed every 30 seconds
- **Detail panel** — click a torrent to display all its information in a side panel
- **Multilingual UI** — French by default, English available via the FR/EN button in the navbar (preference saved in the browser)

## Requirements

- Python 3.10+
- A qBittorrent instance with the Web UI enabled

## Installation

```bash
git clone https://github.com/theOSCARP2/qbittorrent-manager.git
cd qbittorrent-manager
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser, then enter your qBittorrent Web UI URL and credentials.

## Configuration

On first launch, a unique secret key is automatically generated and saved to `~/.qbittorrent-manager/secret.key`. No action required.

| Environment variable | Description |
|---|---|
| `SECRET_KEY` | Overrides the auto-generated key (server, Docker, etc.) |
| `FLASK_DEBUG` | Set to `1` to enable development mode with hot-reload |

The application uses **Waitress** as the production WSGI server (no Flask development warning).

## Credits

Developed with the help of [Claude](https://claude.ai) (Anthropic).

## Notes

- Compatible with qBittorrent v5+ (`/api/v2/torrents/stop` and `start` endpoints, `stoppedUP`/`stoppedDL` states replacing `pausedUP`/`pausedDL`)
- The application stores no credentials — the qBittorrent SID cookie is kept only in the Flask session
