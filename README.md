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

Run scripts from the repository root. The scripts temporarily enter `backend/` and `frontend/`, then return to the original directory even if a command fails.

For real hardware mode:

```powershell
cd mrc_integrated_app
.\scripts\run_real_windows.ps1
```

Real mode expects installed camera and USB3000 drivers and 64-bit Python.

## Hardware Diagnostics

After starting real mode, use these commands in another PowerShell window:

```powershell
curl http://127.0.0.1:7876/status
curl http://127.0.0.1:7876/diagnostics/hardware
```

`/diagnostics/hardware` checks the camera and DAQ separately, so one failing device will not hide the other device's status.

Expected successful camera result:

```json
"camera": {
  "ok": true,
  "status": {
    "mode": "real",
    "initialized": true,
    "device_count": 1
  },
  "error": null
}
```

Expected successful USB3000 result:

```json
"daq": {
  "ok": true,
  "status": {
    "mode": "real",
    "initialized": true,
    "sample_rate_hz": 5000,
    "trigger_channel": 0
  },
  "error": null
}
```

If the camera reports `DXOpenDevice failed with code -3 (unsigned=4294967293, hex=0xFFFFFFFD)`, the SDK saw a camera count but could not open the selected device. Check that:

- the vendor camera demo can open the camera;
- no other program is occupying the camera;
- the camera driver is installed;
- the app is running with 64-bit Python;
- `vendor/camera/x64/` contains the SDK DLL dependencies.

If the diagnostics response lists devices but the selected device fails to open, try a different index:

```powershell
$env:MRC_CAMERA_DEVICE_INDEX="1"
.\scripts\run_real_windows.ps1
```

If the old vendor software that works is 32-bit, also test the vendor x64 demo from the original SDK. This app uses 64-bit Python and the x64 SDK DLLs.

The old `MRC代码/AppExe/VCDemo.exe` is a 32-bit demo. This app uses the x64 SDK. To test the same x64 camera runtime shipped in this repository:

```powershell
.\scripts\run_vendor_camera_x64_demo.ps1
```

If the x64 vendor demo also fails to open the camera while the 32-bit old demo works, install/repair the x64 camera driver/runtime or run this app through a 32-bit helper design. A 64-bit Python process cannot load the 32-bit `DXMediaCap.dll`.

To run the backend with 32-bit Python and the win32/x86 SDK DLLs:

```powershell
.\scripts\setup_windows_x86.ps1
.\scripts\run_real_windows_x86.ps1
```

This keeps Electron/Vue unchanged but starts the Python backend from `backend\.venv32`.
The setup script prefers Python 3.10 32-bit (`py -3.10-32`) and falls back to any installed 32-bit Python (`py -3-32`). The backend code is compatible with Python 3.9 or newer.

To test the committed win32 vendor demo directly:

```powershell
.\scripts\run_vendor_camera_win32_demo.ps1
```

Runtime details can be checked with:

```powershell
curl http://127.0.0.1:7876/diagnostics/runtime
```

The Windows run scripts use backend port `7876` by default. Before startup, they automatically kill any existing process listening on that port. To override the port:

```powershell
$env:MRC_BACKEND_PORT="7877"
.\scripts\run_real_windows.ps1
```

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
