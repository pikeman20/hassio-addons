# Printer Duplex Scan Agent — Home Assistant Addon

Turn any single-sided scanner into a duplex scanning machine — **no hardware upgrade needed**. Just place your document, press Scan, and the addon handles the rest: merging front & back pages, deskewing, PDF generation, duplex printing, card/ID layout, and Telegram notifications.

Built for scanners that support "Scan to FTP" profiles (tested on **Brother MFC-7860DW**, compatible with most Brother MFC/DCP series and other network scanners that support FTP scan profiles).

Core philosophy: reflect physical intent; do not guess, beautify, or auto-center.

## Features

- **Scan duplex** — Pair fronts/backs, interleaved PDF with auto-orientation correction
- **Copy duplex** — Render PDF, print via CUPS two-sided
- **Scan small documents** — Strict 2×2 quadrant layout, respects physical placement
- **Card/ID 2-in-1** — Pair images per page (left-right or top-bottom)
- **Session management** — Explicit Confirm/Reject with timeout fallback and mode switching
- **Web dashboard** — Monitor sessions, view scan history, manage settings
- **Telegram notifications** — Get notified when a session is ready to confirm

## Scan Modes

```
/share/scan_inbox/
 ├─ scan_duplex/      # Duplex scanning with auto-orientation
 ├─ copy_duplex/      # Duplex scanning + auto-print
 ├─ scan_document/    # Multi-document layout (2×2 grid)
 ├─ card_2in1/        # ID/card scanning (2 cards per page)
 ├─ test_print/       # Quick printer test (direct print, no processing)
 ├─ confirm/          # Confirm session processing
 └─ reject/           # Cancel session
```

Each FTP profile on the scanner should point to one of these subfolders.

---

## Quick Start

### Option 1: Home Assistant Addon (Recommended)

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Click the three-dot menu → **Repositories** → add your repository URL
3. Find **Scan Agent** and click **Install**
4. Configure options (FTP credentials, printer, Telegram)
5. Start the addon — the web dashboard is available in the HA sidebar

The addon exposes:
- **Port 2121** — FTP control (scanner uploads)
- **Ports 30000–30002** — FTP passive data ports
- **Ingress** — Web dashboard (accessible from HA sidebar)

### Option 2: Local Python (Development)

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and edit config
cp config.local.template.yaml config.local.yaml

# Start everything (scan agent + FTP server port 2121 + web UI port 8099)
python run.py

# Windows: double-click start.bat

# Selective startup
python run.py --no-ftp          # agent + web UI only
python run.py --no-web          # agent + FTP only
python run.py --no-ftp --no-web # agent only
python run.py --setup           # create config + dirs, don't start
```

The orchestrator automatically creates `scan_inbox/`, `scan_out/`, logs all output to `./logs/`, and handles graceful shutdown on Ctrl+C.

### Option 3: Docker (standalone, no Home Assistant required)

```bash
# Copy and edit config
cp config.local.template.yaml test_data/config.yaml

# Build
docker build -f Dockerfile.local -t scan-agent .

# Run
docker run --rm \
  -v "$PWD/scan_inbox:/share/scan_inbox" \
  -v "$PWD/scan_out:/share/scan_out" \
  -v "$PWD/test_data/config.yaml:/data/config.yaml:ro" \
  -v "$PWD/checkpoints:/app/checkpoints" \
  -p 2121:2121 -p 8099:8099 \
  -p 30000:30000 -p 30001:30001 -p 30002:30002 \
  scan-agent
# Web UI: http://localhost:8099
```

Uses `Dockerfile.local` with a standard Python base image — no Home Assistant or s6-overlay needed.

---

## Scanner Configuration

Set up an FTP profile on your scanner for each scan mode:

| Profile | Remote Path |
|---------|-------------|
| Scan Duplex | `/scan_duplex` |
| Copy Duplex | `/copy_duplex` |
| Scan Document | `/scan_document` |
| Card 2-in-1 | `/card_2in1` |

- **Server**: machine IP running Scan Agent
- **Port**: 2121
- **Username/Password**: as configured in addon options / `config.local.yaml` (or leave blank for anonymous)

> On Brother scanners: **Menu → Network → Scan to FTP → FTP Profiles**. Other brands with FTP scan support (Canon imageRUNNER, Ricoh, Lexmark, etc.) use similar menus under "Scan to Network" or "Scan to FTP".

---

## Folder Structure

```
scan_inbox/
├── scan_duplex/      # Front/back scans (auto-paired)
├── copy_duplex/      # Scan + auto-print
├── scan_document/    # Multi-document 2×2 grid layout
├── card_2in1/        # ID cards (2 per page)
├── test_print/       # Direct PDF print (no processing)
├── confirm/          # Files here trigger session processing
└── reject/           # Files here cancel session

scan_out/
└── Generated PDFs and metadata JSON files
```

---

## Notes

- Duplex scan assumes user scans fronts first, then backs; images are interleaved as `1F, 1B, 2F, 2B, ...`
- Card 2-in-1 pairs two images per page: landscape → left-right, portrait → top-bottom
- Scan Document uses a 2×2 logical grid placed by bounding box center — no auto-centering
- Confirm/Reject is triggered by any file arriving in the `confirm/` or `reject/` folder
- Printing uses CUPS `lp` and only works on Linux (inside the container)
- Background removal requires ONNX models in `checkpoints/` — see `plans/model-dependencies.md`

## License

Internal deployment; no external license headers added.

