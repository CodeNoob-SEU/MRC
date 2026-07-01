from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import ctypes
import math
import os
import platform
import time
from typing import List, Optional

from ..config import DaqConfig, resolve_path


class DaqError(RuntimeError):
    pass


USB3000_ERROR_CODES = {
    -1: "NO_USBDAQ",
    -2: "DevIndex_Overflow",
    -3: "Bad_Firmware",
    -4: "USBDAQ_Closed",
    -5: "Transfer_Data_Fail",
    -6: "NO_Enough_Memory",
    -7: "Time_Out",
    -8: "Not_Reading",
    -9: "ChanIndex_Overflow",
    -10: "Undefined_AiRange",
    -11: "Undefined_SamplePeriod",
    -12: "Undefined_AiConnectType",
    -13: "Undefined_AiSampleMode",
    -14: "Undefined_WaveLen",
    -15: "Undefined_Paramter",
    -16: "USBDAQ_been_Opened",
}


@dataclass
class DaqStatus:
    mode: str
    initialized: bool = False
    sampling: bool = False
    sample_rate_hz: int = 5000
    trigger_channel: int = 0
    sample0_monotonic_ns: Optional[int] = None


@dataclass
class TriggerDetection:
    sample_number: int
    value: float


class TriggerDetector:
    def __init__(self, threshold: float, debounce_seconds: float, sample_rate_hz: int) -> None:
        self.threshold = threshold
        self.debounce_samples = max(1, int(round(debounce_seconds * sample_rate_hz)))
        self.sample_rate_hz = sample_rate_hz
        self.last_high = False
        self.last_trigger_sample: Optional[int] = None

    def process(self, samples: List[float], batch_start_sample: int) -> List[TriggerDetection]:
        detections: List[TriggerDetection] = []
        for index, value in enumerate(samples):
            high = value > self.threshold
            if high and not self.last_high:
                sample_number = batch_start_sample + index
                if (
                    self.last_trigger_sample is None
                    or sample_number - self.last_trigger_sample >= self.debounce_samples
                ):
                    detections.append(TriggerDetection(sample_number=sample_number, value=value))
                    self.last_trigger_sample = sample_number
            self.last_high = high
        return detections


class BaseDaq:
    def initialize(self) -> DaqStatus:
        raise NotImplementedError

    def start_sampling(self) -> DaqStatus:
        raise NotImplementedError

    def read_batch(self) -> List[float]:
        raise NotImplementedError

    def stop_sampling(self) -> DaqStatus:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def status(self) -> DaqStatus:
        raise NotImplementedError


class MockDaq(BaseDaq):
    def __init__(self, config: DaqConfig) -> None:
        self.config = config
        self._status = DaqStatus(
            mode="mock",
            sample_rate_hz=config.sample_rate_hz,
            trigger_channel=config.trigger_channel,
        )
        self._sample_number = 0
        self._next_trigger_sample = int(config.sample_rate_hz * config.mock_trigger_interval_seconds)
        self._pulse_width_samples = max(3, int(config.sample_rate_hz * 0.005))

    def _reset_samples(self) -> None:
        self._sample_number = 0
        self._next_trigger_sample = int(self.config.sample_rate_hz * self.config.mock_trigger_interval_seconds)

    def initialize(self) -> DaqStatus:
        self._status.initialized = True
        return self.status()

    def start_sampling(self) -> DaqStatus:
        if not self._status.initialized:
            self.initialize()
        self._reset_samples()
        self._status.sample0_monotonic_ns = time.monotonic_ns()
        self._status.sampling = True
        return self.status()

    def read_batch(self) -> List[float]:
        if not self._status.sampling:
            raise DaqError("Mock DAQ is not sampling.")
        batch: List[float] = []
        for i in range(self.config.batch_points):
            sample = self._sample_number + i
            phase = sample / self.config.sample_rate_hz
            value = 0.04 * math.sin(phase * math.tau * 8.0)
            if self._next_trigger_sample <= sample < self._next_trigger_sample + self._pulse_width_samples:
                value = 5.0
            batch.append(value)
        self._sample_number += self.config.batch_points
        while self._next_trigger_sample < self._sample_number:
            self._next_trigger_sample += int(
                self.config.sample_rate_hz * self.config.mock_trigger_interval_seconds
            )
        time.sleep(self.config.batch_points / self.config.sample_rate_hz)
        return batch

    def stop_sampling(self) -> DaqStatus:
        self._status.sampling = False
        return self.status()

    def close(self) -> None:
        self._status.sampling = False
        self._status.initialized = False
        self._status.sample0_monotonic_ns = None

    def status(self) -> DaqStatus:
        return replace(self._status)


class USB3000Daq(BaseDaq):
    def __init__(self, config: DaqConfig, repo_root: Path) -> None:
        self.config = config
        self.repo_root = repo_root
        self.dll_path = resolve_path(config.usb3000_dll, repo_root)
        self._dll: Optional[ctypes.CDLL] = None
        self._status = DaqStatus(
            mode="real",
            sample_rate_hz=config.sample_rate_hz,
            trigger_channel=config.trigger_channel,
        )
        self._buffer_type = ctypes.c_float * max(config.batch_points, 160000)
        self._buffer = self._buffer_type()

    def _load(self) -> ctypes.CDLL:
        if platform.system() != "Windows":
            raise DaqError("USB3000.dll can only be loaded on Windows.")
        if not self.dll_path.exists():
            raise DaqError(f"USB3000.dll not found: {self.dll_path}")
        if self._dll is None:
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(self.dll_path.parent))
            win_dll = getattr(ctypes, "WinDLL", None)
            if win_dll is None:
                raise DaqError("ctypes.WinDLL is not available in this Python runtime.")
            self._dll = win_dll(str(self.dll_path))
            self._configure_signatures(self._dll)
        return self._dll

    @staticmethod
    def _configure_signatures(dll: ctypes.CDLL) -> None:
        dll.USB3OpenDevice.argtypes = [ctypes.c_int]
        dll.USB3OpenDevice.restype = ctypes.c_int
        dll.USB3CloseDevice.argtypes = [ctypes.c_int]
        dll.USB3CloseDevice.restype = ctypes.c_int
        dll.SetUSB3AiChanSel.argtypes = [ctypes.c_int, ctypes.c_ubyte, ctypes.c_ubyte]
        dll.SetUSB3AiChanSel.restype = ctypes.c_int
        dll.SetUSB3AiRange.argtypes = [ctypes.c_int, ctypes.c_ubyte, ctypes.c_float]
        dll.SetUSB3AiRange.restype = ctypes.c_int
        dll.SetUSB3AiSampleMode.argtypes = [ctypes.c_int, ctypes.c_ubyte]
        dll.SetUSB3AiConnectType.argtypes = [ctypes.c_int, ctypes.c_ubyte]
        dll.SetUSB3AiSampleRate.argtypes = [ctypes.c_int, ctypes.c_uint]
        dll.SetUSB3AiTrigSource.argtypes = [ctypes.c_int, ctypes.c_ubyte]
        dll.SetUSB3AiConvSource.argtypes = [ctypes.c_int, ctypes.c_ubyte]
        dll.SetUSB3ClrAiFifo.argtypes = [ctypes.c_int]
        dll.SetUSB3AiSoftTrig.argtypes = [ctypes.c_int]
        dll.USB3GetAi.argtypes = [
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_long,
        ]
        dll.USB3GetAi.restype = ctypes.c_int

    def _check(self, result: int, operation: str) -> None:
        if result < 0:
            label = USB3000_ERROR_CODES.get(result, "Unknown")
            raise DaqError(f"{operation} failed with code {result} ({label})")

    def initialize(self) -> DaqStatus:
        dll = self._load()
        dev = self.config.device_index
        self._check(dll.USB3OpenDevice(dev), "USB3OpenDevice")
        for channel in range(8):
            self._check(dll.SetUSB3AiChanSel(dev, channel, 0), "SetUSB3AiChanSel")
        self._check(dll.SetUSB3AiChanSel(dev, self.config.trigger_channel, 1), "SetUSB3AiChanSel")
        self._check(dll.SetUSB3AiRange(dev, self.config.trigger_channel, self.config.ai_range), "SetUSB3AiRange")
        self._check(dll.SetUSB3AiSampleMode(dev, 0), "SetUSB3AiSampleMode")
        self._check(dll.SetUSB3AiConnectType(dev, 1), "SetUSB3AiConnectType")
        self._check(dll.SetUSB3AiSampleRate(dev, self.config.sample_period), "SetUSB3AiSampleRate")
        self._check(dll.SetUSB3AiTrigSource(dev, 0), "SetUSB3AiTrigSource")
        self._check(dll.SetUSB3AiConvSource(dev, 0), "SetUSB3AiConvSource")
        self._status.initialized = True
        return self.status()

    def start_sampling(self) -> DaqStatus:
        if not self._status.initialized:
            self.initialize()
        assert self._dll is not None
        dev = self.config.device_index
        self._check(self._dll.SetUSB3ClrAiFifo(dev), "SetUSB3ClrAiFifo")
        self._check(self._dll.SetUSB3AiSoftTrig(dev), "SetUSB3AiSoftTrig")
        self._status.sample0_monotonic_ns = time.monotonic_ns()
        self._status.sampling = True
        return self.status()

    def read_batch(self) -> List[float]:
        if self._dll is None or not self._status.sampling:
            raise DaqError("USB3000 DAQ is not sampling.")
        result = self._dll.USB3GetAi(
            self.config.device_index,
            self.config.batch_points,
            self._buffer,
            self.config.timeout_ms,
        )
        self._check(result, "USB3GetAi")
        return [float(self._buffer[i]) for i in range(self.config.batch_points)]

    def stop_sampling(self) -> DaqStatus:
        self._status.sampling = False
        return self.status()

    def close(self) -> None:
        if self._dll is not None and self._status.initialized:
            self._dll.USB3CloseDevice(self.config.device_index)
        self._status.initialized = False
        self._status.sampling = False
        self._status.sample0_monotonic_ns = None

    def status(self) -> DaqStatus:
        return replace(self._status)


def build_daq(mode: str, config: DaqConfig, repo_root: Path) -> BaseDaq:
    if mode == "real":
        return USB3000Daq(config, repo_root)
    if mode == "auto" and platform.system() == "Windows":
        return USB3000Daq(config, repo_root)
    return MockDaq(config)
