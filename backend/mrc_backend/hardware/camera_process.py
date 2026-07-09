"""Process isolation for the vendor camera SDK.

The DXMediaCap DLL can wedge a thread inside an uncancellable kernel call
when the device drops (unplugged mid-run). A thread stuck like that cannot
be reaped by TerminateProcess, so if it lives in the backend process the
whole backend becomes unkillable until the driver times out internally.

This module runs each camera's SDK inside a dedicated child process. The
backend talks to it over a pipe with per-call timeouts; when the child
wedges it is terminated and respawned. A wedged child may linger as an
orphan until the driver lets go, but the backend itself always stays
responsive and can always exit.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
import importlib
import json
import logging
import multiprocessing
import os
import platform
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, Optional, Tuple

from ..config import CameraConfig
from .camera import BaseCamera, CameraError, CameraStatus, DXMediaCamera

_LOGGER = logging.getLogger("mrc_backend.camera_process")

_WORKER_PIDFILE_DIR = Path(tempfile.gettempdir()) / "mrc_camera_workers"

_EXIT_METHOD = "__exit__"


def _default_camera_factory(config: CameraConfig, repo_root: Path) -> BaseCamera:
    return DXMediaCamera(config, repo_root)


def _write_worker_pidfile() -> Optional[Path]:
    try:
        _WORKER_PIDFILE_DIR.mkdir(parents=True, exist_ok=True)
        pidfile = _WORKER_PIDFILE_DIR / f"{os.getpid()}.json"
        pidfile.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "backend_pid": os.getppid(),
                    "created_at": time.time(),
                }
            ),
            encoding="utf-8",
        )
        return pidfile
    except OSError:
        return None


def _pid_is_running_python(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if platform.system() == "Windows":
            completed = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return "python" in completed.stdout.lower()
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return "python" in completed.stdout.lower()
    except Exception:  # noqa: BLE001
        return False


def _force_kill_pid(pid: int) -> None:
    try:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                check=False,
            )
        else:
            os.kill(pid, 9)
    except Exception:  # noqa: BLE001
        pass


def sweep_stale_camera_workers() -> None:
    """Kill camera workers left behind by a previous backend run.

    A worker whose owning backend is still alive is left alone, so two
    backends running side by side do not kill each other's workers.
    """
    if not _WORKER_PIDFILE_DIR.exists():
        return
    for pidfile in _WORKER_PIDFILE_DIR.glob("*.json"):
        try:
            data = json.loads(pidfile.read_text(encoding="utf-8"))
            pid = int(data.get("pid", 0))
            backend_pid = int(data.get("backend_pid", 0))
        except Exception:  # noqa: BLE001
            pidfile.unlink(missing_ok=True)
            continue
        if backend_pid and backend_pid != os.getpid() and _pid_is_running_python(backend_pid):
            continue
        if _pid_is_running_python(pid):
            _LOGGER.warning("Killing stale camera worker from a previous run (pid=%d).", pid)
            _force_kill_pid(pid)
        pidfile.unlink(missing_ok=True)


def _camera_worker_entry(
    conn: Any,
    config_dict: Dict[str, Any],
    repo_root_text: str,
    factory_module: str,
    factory_name: str,
) -> None:
    pidfile = _write_worker_pidfile()
    camera: Optional[BaseCamera] = None
    try:
        module = importlib.import_module(factory_module)
        factory = getattr(module, factory_name)
        camera = factory(CameraConfig(**config_dict), Path(repo_root_text))
        while True:
            try:
                request_id, method, args = conn.recv()
            except (EOFError, OSError):
                # Backend is gone; exit quietly. Skipping camera.close() is
                # deliberate: a dead device could hang this process's exit.
                break
            if method == _EXIT_METHOD:
                try:
                    camera.close()
                except Exception:  # noqa: BLE001
                    pass
                _safe_send(conn, (request_id, True, None))
                break
            try:
                if method == "start_recording":
                    result: Any = camera.start_recording(Path(args[0]))
                elif method == "preview_frame_data_url":
                    result = camera.preview_frame_data_url()
                elif method == "enumerate_devices":
                    result = getattr(camera, "enumerate_devices")()
                elif method in {"initialize", "stop_recording", "reconnect"}:
                    result = getattr(camera, method)()
                elif method == "status":
                    result = camera.status()
                else:
                    raise CameraError(f"unknown camera worker method: {method}")
                _safe_send(conn, (request_id, True, result))
            except Exception as exc:  # noqa: BLE001
                _safe_send(conn, (request_id, False, f"{exc}"))
    finally:
        if pidfile is not None:
            try:
                pidfile.unlink(missing_ok=True)
            except OSError:
                pass


def _safe_send(conn: Any, payload: Tuple[int, bool, Any]) -> None:
    try:
        conn.send(payload)
    except (OSError, BrokenPipeError, ValueError):
        pass


class CameraProcessProxy(BaseCamera):
    """Drives a camera hosted in a child process, with per-call timeouts."""

    _CALL_TIMEOUTS: Dict[str, float] = {
        "initialize": 30.0,
        "enumerate_devices": 15.0,
        "start_recording": 20.0,
        "stop_recording": 10.0,
        "preview_frame_data_url": 3.0,
    }
    _INITIALIZE_ATTEMPTS = 2
    _INITIALIZE_RETRY_WAIT_SECONDS = 2.5

    def __init__(
        self,
        config: CameraConfig,
        repo_root: Path,
        factory: Tuple[str, str] = ("mrc_backend.hardware.camera_process", "_default_camera_factory"),
        timeout_overrides: Optional[Dict[str, float]] = None,
    ) -> None:
        self._config = config
        self._repo_root = repo_root
        self._factory = factory
        self._timeouts = {**self._CALL_TIMEOUTS, **(timeout_overrides or {})}
        self._ctx = multiprocessing.get_context("spawn")
        self._proc: Optional[multiprocessing.process.BaseProcess] = None
        self._conn: Any = None
        self._rpc_lock = threading.Lock()
        self._request_id = 0
        self._cached_status = CameraStatus(mode="real")

    # ------------------------------------------------------------------
    # BaseCamera interface
    # ------------------------------------------------------------------

    def status(self) -> CameraStatus:
        # Served from cache so status polling never blocks on (or spawns)
        # the worker; the cache updates on every successful control call.
        return replace(self._cached_status)

    def initialize(self) -> CameraStatus:
        last_error: Optional[CameraError] = None
        for attempt in range(1, self._INITIALIZE_ATTEMPTS + 1):
            try:
                return self._call("initialize", spawn_if_needed=True)
            except CameraError as exc:
                last_error = exc
                # After a replug the driver may need a moment to settle;
                # retry once on a fresh worker.
                self._terminate_worker()
                if attempt < self._INITIALIZE_ATTEMPTS:
                    time.sleep(self._INITIALIZE_RETRY_WAIT_SECONDS)
        assert last_error is not None
        raise last_error

    def start_recording(self, output_file: Path) -> CameraStatus:
        return self._call("start_recording", args=(str(output_file),))

    def stop_recording(self) -> CameraStatus:
        return self._call("stop_recording")

    def preview_frame_data_url(self) -> Optional[str]:
        with self._rpc_lock:
            worker_ready = self._proc is not None and self._proc.is_alive()
        if not worker_ready or not self._cached_status.initialized:
            return None
        return self._call("preview_frame_data_url")

    def enumerate_devices(self) -> Any:
        return self._call("enumerate_devices", spawn_if_needed=True)

    def reconnect(self) -> CameraStatus:
        # Process-level reconnect: abandon the (possibly wedged) worker and
        # rebuild the SDK session in a fresh process.
        self._terminate_worker()
        return self.initialize()

    def close(self) -> None:
        with self._rpc_lock:
            proc = self._proc
            if proc is None:
                return
            if proc.is_alive() and self._conn is not None:
                try:
                    self._request_id += 1
                    self._conn.send((self._request_id, _EXIT_METHOD, []))
                    self._conn.poll(3.0)
                except (OSError, BrokenPipeError, ValueError):
                    pass
            self._terminate_worker_locked()

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------

    def _spawn_worker_locked(self) -> None:
        self._close_conn_locked()
        parent_conn, child_conn = self._ctx.Pipe()
        proc = self._ctx.Process(
            target=_camera_worker_entry,
            args=(
                child_conn,
                asdict(self._config),
                str(self._repo_root),
                self._factory[0],
                self._factory[1],
            ),
            name="mrc-camera-worker",
            daemon=True,
        )
        proc.start()
        child_conn.close()
        self._proc = proc
        self._conn = parent_conn
        _LOGGER.info("Camera worker started (pid=%s).", proc.pid)

    def _terminate_worker(self) -> None:
        with self._rpc_lock:
            self._terminate_worker_locked()

    def _terminate_worker_locked(self) -> None:
        proc = self._proc
        # Closing the pipe first lets a healthy worker exit on its own.
        self._close_conn_locked()
        if proc is not None and proc.is_alive():
            proc.join(timeout=0.5)
            if proc.is_alive():
                _LOGGER.warning("Terminating camera worker (pid=%s).", proc.pid)
                proc.terminate()
                proc.join(timeout=2.0)
            if proc.is_alive():
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
                proc.join(timeout=1.0)
        self._proc = None
        self._cached_status.initialized = False
        self._cached_status.recording = False

    def _close_conn_locked(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except (OSError, ValueError):
                pass
            self._conn = None

    # ------------------------------------------------------------------
    # RPC
    # ------------------------------------------------------------------

    def _call(self, method: str, args: Tuple[Any, ...] = (), spawn_if_needed: bool = False) -> Any:
        timeout = self._timeouts.get(method, 15.0)
        with self._rpc_lock:
            if self._proc is None or not self._proc.is_alive():
                if not spawn_if_needed:
                    raise CameraError("camera worker process is not running")
                self._spawn_worker_locked()
            conn = self._conn
            proc = self._proc
            assert conn is not None and proc is not None
            # Drop stale replies from previously timed-out calls.
            while conn.poll(0):
                try:
                    conn.recv()
                except (EOFError, OSError):
                    break
            self._request_id += 1
            request_id = self._request_id
            try:
                conn.send((request_id, method, list(args)))
            except (OSError, BrokenPipeError, ValueError) as exc:
                self._terminate_worker_locked()
                raise CameraError(f"camera worker pipe failed: {exc}") from exc
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if method != "preview_frame_data_url":
                        # A timed-out control call means the SDK wedged;
                        # abandon the worker so the backend stays healthy.
                        self._terminate_worker_locked()
                    raise CameraError(
                        f"camera worker call '{method}' timed out after {timeout:.1f}s"
                    )
                if conn.poll(min(remaining, 0.2)):
                    try:
                        reply_id, ok, payload = conn.recv()
                    except (EOFError, OSError) as exc:
                        self._terminate_worker_locked()
                        raise CameraError("camera worker exited unexpectedly") from exc
                    if reply_id != request_id:
                        continue
                    if not ok:
                        raise CameraError(str(payload))
                    if isinstance(payload, CameraStatus):
                        self._cached_status = payload
                    return payload
                if not proc.is_alive():
                    self._terminate_worker_locked()
                    raise CameraError("camera worker died during the call")
