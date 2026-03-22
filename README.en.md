# qBittorrent Manager

A lightweight Flask web interface to manage a remote qBittorrent instance.

> 🇫🇷 [Version française](README.md)

## Screenshots

![Torrent list](docs/torrents.png)
![Tracker management](docs/trackers.png)

## Features

- **Torrent list** — paginated, sortable and searchable table (server-side DataTables)
- **Torrent actions** — pause, resume, recheck, delete (with or without files)
- **Tracker view** — list of all trackers across all torrents with OK/error/pending status
- **Bulk tracker operations** — add, replace, remove or copy a tracker URL across all torrents (including adding a tracker to all torrents that share a source tracker)
- **Background cache** — torrent list is cached and automatically refreshed every 30 seconds
- **Detail panel** — click a torrent to display all its information in a side panel
- **Multilingual UI** — French by default, English available via the FR/EN button in the navbar (preference saved in the browser)
- **Dashboard** — overview with global speeds, disk usage (used/available with progress bar), real-time speed chart, torrent breakdown by state and category (count and disk space)
- **Persistent filters** — filter torrents by state and category, filter trackers by status (OK / error / pending); sort and filters saved in the browser
- **Dark / light theme** — toggle via the sun/moon button in the navbar, preference saved in the browser
- **File priority** — dropdown per file in the detail panel (Skip / Normal / High / Maximum)
- **Debug mode** — toggle from the web UI (🐛 button in navbar), shows verbose logs in the console without restarting
- **Add torrents** — add a torrent via magnet link/URL or .torrent file, with category, save path and pause options
- **Category change** — change a torrent's category directly from the detail panel
- **Trackers in detail panel** — tracker list with status icon (active / error / pending)
- **Filters integrated in table** — state and category filters directly in column headers
- **Update check** — navbar badge if a newer version is available on GitHub
- **Browser notifications** — automatic alert when a torrent reaches 100%
- **File list** — per-file details (name, size, individual progress bar) in the torrent detail panel
- **ETA column** — estimated time remaining in the torrent table (sortable)
- **Categories page** — full category management: create, rename, change save path, move torrents between categories, delete
- **Logs page** — real-time qBittorrent logs with level filter (Normal / Info / Warning / Critical), pause and auto-scroll

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

### From binaries (recommended)

Download the binary for your system from the [Releases](https://github.com/theOSCARP2/qbittorrent-manager/releases) page:

| System | File |
|---|---|
| Windows | `qbittorrent-manager.exe` |
| Linux | `qbittorrent-manager-linux` |
| macOS (Apple Silicon M1/M2/M3) | `qbittorrent-manager-macos-arm64` |
| macOS (Intel) | `qbittorrent-manager-macos-intel` |

**Windows** — double-click the `.exe` or run it from a terminal:
```bat
qbittorrent-manager.exe
```

**Linux / macOS** — make the file executable then run it:
```bash
chmod +x qbittorrent-manager-linux  # or qbittorrent-manager-macos-arm64 / qbittorrent-manager-macos-intel
./qbittorrent-manager-linux
```

### From source

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser, then enter your qBittorrent Web UI URL and credentials.

## Configuration

On first launch, a unique secret key is automatically generated and saved to `~/.qbittorrent-manager/secret.key`. No action required.

| Environment variable | Description |
|---|---|
| `SECRET_KEY` | Overrides the auto-generated key (server, Docker, etc.) |

The application uses **Waitress** as the production WSGI server (no Flask development warning).

## Credits

Developed with the help of [Claude](https://claude.ai) (Anthropic).

## Notes

- Compatible with qBittorrent v5+ (`/api/v2/torrents/stop` and `start` endpoints, `stoppedUP`/`stoppedDL` states replacing `pausedUP`/`pausedDL`)
- The application stores no credentials — the qBittorrent SID cookie is kept only in the Flask session
