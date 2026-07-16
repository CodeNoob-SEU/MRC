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
.\scripts\init_windows.ps1
.\scripts\run_windows.ps1
```

Run scripts from the repository root. The scripts temporarily enter `backend/` and `frontend/`, then return to the original directory even if a command fails.

`init_windows.ps1` is the one-time new-machine setup script. It installs the bundled Windows ffmpeg runtime, creates `backend\.venv32` with 32-bit Python, installs Python and Node dependencies, and runs a build check.

`run_windows.ps1` is the normal startup script. By default it runs real hardware mode with the win32 camera SDK, backend port `7876`, camera device `0`, DAQ device `0`, AV1/source `0`, NTSC `720x480 @ 30 fps`, and MP4 capture.

Useful run options:

```powershell
.\scripts\run_windows.ps1 -VideoSourceIndex 1
.\scripts\run_windows.ps1 -EnableCamera2
.\scripts\run_windows.ps1 -EnableCamera2 -Camera2DeviceIndex 1 -VideoSourceIndex2 0
.\scripts\run_windows.ps1 -CaptureFormat avi
.\scripts\run_windows.ps1 -Mode mock
```

Real mode expects installed camera and USB3000 drivers. This project defaults to 32-bit Python on Windows because the working vendor demo and SDK path are win32.

## Build A Portable Windows x64 EXE

On macOS or Linux with Node.js and Python 3 installed:

```bash
cd frontend
npm install
npm run dist:win:x64
```

The build downloads and bundles the Windows x86 Python backend required by the
camera SDK, bundles FFmpeg and the hardware runtime DLLs, and produces:

```text
frontend/release/MRC-Integrated-Acquisition-0.1.0-Windows-x64.exe
```

The Electron application is Windows x64. The bundled backend remains x86 so it
can load the working win32 camera and DAQ SDKs. Target machines still need the
vendor hardware drivers installed.

## Hardware Diagnostics

After starting real mode, use these commands in another PowerShell window:

```powershell
curl http://127.0.0.1:7876/status
curl http://127.0.0.1:7876/diagnostics/hardware
```

`/diagnostics/hardware` checks the camera and DAQ separately, so one failing device will not hide the other device's status.

## Troubleshooting: Green Preview / Device Won't Open (无需重启电脑)

Two field-confirmed failure modes share the same root cause and the same fix.
A camera-worker process that wedged inside an uncancellable kernel call of the
capture driver survives `taskkill /F` and keeps the driver's capture channel
occupied. Symptoms:

1. **纯绿画面** — the pipeline runs but the driver only delivers zeroed YUV
   buffers (an untouched buffer decodes to solid green).
2. **新会话打不开设备** — a fresh app start fails to initialize the camera
   because the zombie still holds the device.

Do NOT reboot. Reset the capture device instead — the PnP disable/enable
cycle forces the driver to cancel its outstanding I/O, which lets the stuck
thread return and the zombie terminate within seconds:

```powershell
# Run PowerShell as Administrator
.\scripts\reset_capture_device_windows.ps1                      # first time: list devices
.\scripts\reset_capture_device_windows.ps1 -NameLike "*Video*"  # reset the matching device
```

Physically unplugging and replugging the capture device achieves the same
thing. After the reset, confirm in Task Manager that the leftover python
process is gone, then start the app again.

Prevention: in Device Manager, disable "Allow the computer to turn off this
device to save power" for the capture device and USB root hubs, and turn off
USB selective suspend in the power plan. Plug the capture device into a
motherboard USB port rather than a shared hub.

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
- the app was initialized with `.\scripts\init_windows.ps1`;
- the app is running with the default win32 SDK path from `.\scripts\run_windows.ps1`.

If the diagnostics response lists devices but the selected device fails to open, try a different index:

```powershell
.\scripts\run_windows.ps1 -CameraDeviceIndex 1
```

The normal Windows path uses 32-bit Python and the win32 SDK because the working vendor demo is 32-bit. The old lower-level x86 scripts are still available for debugging:

```powershell
.\scripts\setup_windows_x86.ps1
.\scripts\run_real_windows_x86.ps1
```

The consolidated scripts are preferred for a new machine:

```powershell
.\scripts\init_windows.ps1
.\scripts\run_windows.ps1
```

Before setup, verify that the Python launcher can find a 32-bit runtime:

```powershell
py -0p
py -3.10-32 --version
```

The setup script prefers Python 3.10 32-bit (`py -3.10-32`) and falls back to any installed 32-bit Python (`py -3-32`). The backend code is compatible with Python 3.9 or newer.

If `py -3.10-32` is not available, install the Windows x86 Python installer from python.org. You can also point the setup script at a specific 32-bit Python executable:

```powershell
$env:MRC_PYTHON32="C:\Users\dell\AppData\Local\Programs\Python\Python310-32\python.exe"
.\scripts\init_windows.ps1
```

To test the committed win32 vendor demo directly:

```powershell
.\scripts\run_vendor_camera_win32_demo.ps1
```

To compare the x64 vendor runtime manually:

```powershell
.\scripts\run_vendor_camera_x64_demo.ps1
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
- `MRC_CAMERA_PREVIEW_FPS=0` makes the Electron preview snapshot rate follow the camera capture FPS. Set it to a positive number such as `15` only when you need to throttle preview CPU/network cost.

The Python camera adapter follows the working VC demo order: `DXOpenDevice`, `DXSetVideoSourceEx`, `DXSetVideoPara`, `DXDeviceRunEx`, `DXGetVideoPara`, `DXSetVideoSourceEx` again, then preview via `DXGetBuf`. Recording follows `DeviceControl::StartRecord`: `DXSetVideoCodec`, `DXSetVideoCodecPara`, `DXSetAudioCodec`, `DXStartCapture`.

To test AV2 in the main app:

```powershell
.\scripts\run_windows.ps1 -VideoSourceIndex 1
```

To enable a second capture card for camera 2:

```powershell
.\scripts\run_windows.ps1 -EnableCamera2 -CameraDeviceIndex 0 -Camera2DeviceIndex 1
```

Camera 2 inherits camera 1's connection and capture settings by default. Only the device index changes from `0` to `1`. If the second card needs a different AV input, override it explicitly:

```powershell
.\scripts\run_windows.ps1 -EnableCamera2 -VideoSourceIndex2 1
```

When camera 2 is enabled, the right-top video panel shows its live preview. Trigger recording writes:

```text
mrc_recording.mp4
mrc_recording_camera2.mp4
mrc_recording_aligned.mp4
mrc_recording_camera2_aligned.mp4
```

`alignment.json` keeps the existing camera 1 fields and adds `cameras.camera2`, `camera2_video_trim`, `camera2_video_validation`, and `camera2_frame_extract`.

If MP4 recording still fails on a specific machine, test AVI without changing code:

```powershell
.\scripts\run_windows.ps1 -CaptureFormat avi
```

The UI supports two recording modes:

- `Trigger录制`: starts camera recording and DAQ sampling, then uses the first Trigger as t0 for synchronized outputs.
- `手动录制`: starts and stops camera recording only. It writes the video, `config_snapshot.json`, and `events.jsonl`, but does not write `alignment.json`, `frame_map.csv`, or Trigger tables.

After `Trigger录制` finishes, the backend keeps the original preroll video and tries to create an aligned video whose first frame is the first Trigger t0:

```text
mrc_recording.mp4
mrc_recording_aligned.mp4
```

Automatic trimming uses `ffmpeg`. Install it into `PATH`, or set an explicit path:

```powershell
$env:MRC_FFMPEG="C:\Tools\ffmpeg\bin\ffmpeg.exe"
.\scripts\run_windows.ps1
```

The Windows initialization script installs a bundled ffmpeg runtime automatically:

```powershell
.\scripts\init_windows.ps1
```

That creates:

```text
vendor\ffmpeg\windows\bin\ffmpeg.exe
```

The run script prefers this bundled executable when `MRC_FFMPEG` is not already set.

By default trimming uses re-encoding for a more accurate t0 cut, with stream-copy as a fallback. To force faster keyframe-based stream copy:

```powershell
$env:MRC_VIDEO_TRIM_MODE="copy"
.\scripts\run_windows.ps1
```

If `ffmpeg` is not available, the experiment still completes and records the reason under `alignment.json` -> `video_trim`.
When ffmpeg is available, the backend also extracts `aligned_first_frame.jpg` and `aligned_last_frame.jpg` into the same experiment output folder for timing checks. Extraction details are recorded under `alignment.json` -> `frame_extract`.

After the DAQ reaches the theoretical Trigger window end, the app stops DAQ sampling but keeps the camera recording for an extra post-window buffer. The default is 1 second:

```powershell
$env:MRC_POST_WINDOW_RECORD_SECONDS="1"
.\scripts\run_windows.ps1
```

This extra video is only source material for trimming. `alignment.json`, `frame_map.csv`, and `mrc_recording_aligned.mp4` still use the theoretical window length, for example `60.000 s` and `1800` frames at 30 FPS.

The Windows run scripts use backend port `7876` by default. Before startup, they automatically kill any existing process listening on that port. To override the port:

```powershell
.\scripts\run_windows.ps1 -Port 7877
```

Backend shutdown is deadline-protected because some camera SDK calls can block during preview/capture teardown. By default the backend waits up to 4 seconds for graceful hardware cleanup, then forces the Python process to exit so the port is released:

```powershell
$env:MRC_SHUTDOWN_TIMEOUT_SECONDS="4"
.\scripts\run_windows.ps1
```

On Windows, the normal run script enables fast backend shutdown:

```powershell
$env:MRC_FAST_BACKEND_SHUTDOWN="1"
```

Fast shutdown skips camera SDK teardown calls such as `DXStopPreview`, `DXDeviceStop`, `DXCloseDevice`, and `DXUninitialize` during application exit. This avoids the most common DirectShow/driver hang path. Stop the experiment from the UI before closing the app so the recording file is finalized first. To debug full SDK cleanup, set:

```powershell
$env:MRC_FAST_BACKEND_SHUTDOWN="0"
.\scripts\run_windows.ps1
```

Electron first asks the backend to use fast shutdown, then falls back to `taskkill /T /F` only if the backend does not exit. If a stale backend is still listening before startup, `scripts\ensure_backend_port_windows.ps1` kills the listener PID before launching a new backend.

If Windows reports `Access is denied` while killing the backend, the stale process was usually started from an elevated or different user session. Run the system-level cleanup script from the repository root:

```powershell
.\scripts\cleanup_windows_admin.ps1 -Port 7876
```

The script asks for Administrator privileges when needed, finds the backend listener on port `7876`, follows its child process tree, and also removes MRC-related Python/Electron/Node processes whose command line points at this repository. If the process is still stuck, it tries to reset matching PnP capture devices:

```powershell
.\scripts\cleanup_windows_admin.ps1 -Port 7876 -DeviceNamePattern "ZhongAn|US2000|Video Capture"
```

Use `Get-PnpDevice | Where-Object FriendlyName -match "Video|Capture|ZhongAn|US2000"` to inspect the exact device names on a new PC. If the port is still occupied after process termination and PnP reset, reboot Windows to release a process stuck inside the vendor camera driver.

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
