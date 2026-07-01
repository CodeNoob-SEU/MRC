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

## Standalone Camera Probe

If the camera opens but the Electron preview does not show a valid image, run the standalone camera probe with the app closed:

```powershell
git pull
.\scripts\camera_probe_windows_x86.ps1
```

The probe uses `backend\.venv32` and the committed win32 `DXMediaCap.dll` by default. It tests multiple SDK paths:

- `DXSnapToJPGFile`
- `DXGetFrameBuffer` + `DXSaveJPGFile`
- `DXGetBuf` + `DXSaveJPGFile`
- `DXStartRawVideoCallback` + `DXSaveJPGFile`
- hidden-window `DXStartPreview` modes followed by snapshot
- short MP4 and AVI capture

It tries NTSC profiles first (`720x480 @ 30 fps`, `standard=1`) and keeps PAL profiles as fallbacks. Results are written to:

```text
camera_probe_output\
```

Open the generated JPG files and find the first one that shows a correct camera image. Then check `camera_probe_output\camera_probe_report.json` for the matching profile and strategy name.

To test only one profile:

```powershell
.\scripts\camera_probe_windows_x86.ps1 --profile custom --width 720 --height 480 --fps 30 --standard 1 --colorspace 2
```

For AV1/AV2 input testing, start with the VC demo's source-index API:

```powershell
.\scripts\camera_probe_windows_x86.ps1 --profile custom --width 720 --height 480 --fps 30 --standard 1 --colorspace 2 --sources 0,1 --source-methods ex
.\scripts\camera_probe_windows_x86.ps1 --profile custom --width 640 --height 480 --fps 30 --standard 1 --colorspace 2 --sources 0,1 --source-methods ex
```

If both are still green, test the older legacy source API:

```powershell
.\scripts\camera_probe_windows_x86.ps1 --profile custom --width 720 --height 480 --fps 30 --standard 1 --colorspace 2 --sources 1,2 --source-methods legacy
.\scripts\camera_probe_windows_x86.ps1 --profile custom --width 640 --height 480 --fps 30 --standard 1 --colorspace 2 --sources 1,2 --source-methods legacy
```

In the report, check `signal_after_run.signal`: `1` means that source has a video signal, `0` means signal loss.

To stop after the first non-empty candidate file:

```powershell
.\scripts\camera_probe_windows_x86.ps1 --stop-on-first
```

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

Before setup, verify that the Python launcher can find a 32-bit runtime:

```powershell
py -0p
py -3.10-32 --version
```

If `py -3.10-32` is not available, install the Windows x86 Python installer from python.org. You can also point the setup script at a specific 32-bit Python executable:

```powershell
$env:MRC_PYTHON32="C:\Users\dell\AppData\Local\Programs\Python\Python310-32\python.exe"
.\scripts\setup_windows_x86.ps1
```

To test the committed win32 vendor demo directly:

```powershell
.\scripts\run_vendor_camera_win32_demo.ps1
```

Runtime details can be checked with:

```powershell
curl http://127.0.0.1:7876/diagnostics/runtime
```

Real camera calls are serialized through one dedicated SDK thread because `DXMediaCap.dll` uses DirectShow/COM objects that are sensitive to thread apartment ownership. The default capture settings are aligned with the vendor demos:

- `MRC_CAMERA_WIDTH=720`
- `MRC_CAMERA_HEIGHT=480`
- `MRC_CAMERA_FPS=30`
- `MRC_CAMERA_VIDEO_STANDARD=1` for NTSC. PAL is `32`.
- `MRC_CAMERA_COLORSPACE=2`
- `MRC_CAMERA_CAPTURE_FORMAT=2` for MP4, `1` for AVI
- `MRC_CAMERA_VIDEO_CODEC="x264 Codec"`
- `MRC_CAMERA_VIDEO_SOURCE_INDEX=0` for AV1, `1` for AV2, matching the VC demo's `DXSetVideoSourceEx`
- `MRC_CAMERA_PREVIEW_MODE=2` for D3D, matching `VCdemoSeting.ini`

The Python camera adapter follows the working VC demo order: `DXOpenDevice`, `DXSetVideoSourceEx`, `DXSetVideoPara`, `DXDeviceRunEx`, `DXGetVideoPara`, `DXSetVideoSourceEx` again, then preview via `DXGetBuf`. Recording follows `DeviceControl::StartRecord`: `DXSetVideoCodec`, `DXSetVideoCodecPara`, `DXSetAudioCodec`, `DXStartCapture`.

To test AV2 in the main app:

```powershell
$env:MRC_CAMERA_VIDEO_SOURCE_INDEX="1"
.\scripts\run_real_windows_x86.ps1
```

If MP4 recording still fails on a specific machine, test AVI without changing code:

```powershell
$env:MRC_CAMERA_CAPTURE_FORMAT="1"
.\scripts\run_real_windows_x86.ps1
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
- `alignment.json`
- `frame_map.csv`
- `triggers.csv`
- `triggers.sqlite3`
- `events.jsonl`
- `config_snapshot.json`

`alignment.json` records the DAQ-sample-clock t0, effective FPS, estimated video frame range for the usable imaging window, preroll offset, and stop overshoot. `frame_map.csv` maps each effective frame after the first Trigger to the estimated frame number in the raw video file. `triggers.csv` and `triggers.sqlite3` include both t0-relative frame indexes and estimated raw-video frame indexes.

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
