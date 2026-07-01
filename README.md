# MRC Integrated Acquisition

Electron + Vue desktop shell with a Python FastAPI backend for MRC camera recording and USB3000 trigger acquisition.

This repository is self-contained for source code and hardware runtime DLLs. Python and Node dependencies are installed locally after cloning.

## Layout

- `backend/`: Python service, hardware adapters, experiment coordinator, REST/WebSocket API.
- `frontend/`: Electron + Vue 3 + Vite UI. Electron starts the Python backend process.
- `backend/tests/`: mock-mode tests for trigger detection and experiment output.
- `vendor/`: committed runtime DLLs and SDK headers for Windows hardware testing.
- `scripts/`: Windows setup and run helpers.

## Quick Start On Windows

From a fresh clone:

```powershell
cd mrc_integrated_app
.\scripts\setup_windows.ps1
.\scripts\run_mock_windows.ps1
```

For real hardware mode:

```powershell
cd mrc_integrated_app
.\scripts\run_real_windows.ps1
```

Real mode expects installed camera and USB3000 drivers and 64-bit Python.

## Backend

Create the local virtual environment and install runtime dependencies:

```bash
cd backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Run tests:

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
```

Run the backend directly:

```bash
PYTHONPATH=. .venv/bin/python -m mrc_backend.run_backend
```

The backend defaults to mock hardware. To use the Windows DLL adapters:

```powershell
$env:MRC_HARDWARE_MODE="real"
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m mrc_backend.run_backend
```

The real mode expects 64-bit Python on Windows and the existing DLLs at:

- `vendor/camera/x64/DXMediaCap.dll`
- `vendor/daq/x64/USB3000.dll`

Override paths if needed:

```powershell
$env:MRC_DXMEDIA_DLL="C:\path\to\DXMediaCap.dll"
$env:MRC_USB3000_DLL="C:\path\to\USB3000.dll"
```

## Frontend

Install dependencies and start Electron in development mode:

```bash
cd frontend
npm install --cache .npm-cache
npm run dev
```

Build Vue and Electron sources:

```bash
npm run build
```

Electron starts `backend/.venv` automatically when it exists. Set `MRC_PYTHON` to override the Python executable.

## Data Output

Each experiment creates one timestamped session folder containing:

- `mrc_recording.mp4`
- `triggers.csv`
- `triggers.sqlite3`
- `events.jsonl`
- `config_snapshot.json`

## Git Notes

Committed:

- application source
- `package-lock.json`
- Python requirements
- Windows helper scripts
- hardware DLLs/headers under `vendor/`

Ignored:

- `frontend/node_modules/`
- `frontend/.npm-cache/`
- `backend/.venv/`
- build output
- experiment `runs/`
