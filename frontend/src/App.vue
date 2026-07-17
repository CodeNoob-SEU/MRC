<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import {
  AlertTriangle, FileText, FolderOpen, Play, RotateCw, Save, SlidersHorizontal, Square, Wrench
} from "lucide-vue-next";

/* ----------------------------- Types ----------------------------- */
type HardwareStatus = {
  mode: string;
  initialized: boolean;
  recording?: boolean;
  sampling?: boolean;
  device_count?: number;
  device_name?: string;
  sample_rate_hz?: number;
  trigger_channel?: number;
  width?: number;
  height?: number;
  fps?: number;
  active_file?: string | null;
  capture_status?: string;
  video_source_status?: string;
  preview_status?: string;
  preview_started?: boolean;
};

type AppStatus = {
  state: string;
  recording_mode: string;
  session_id: string | null;
  output_dir: string | null;
  video_file: string | null;
  video_file2: string | null;
  aligned_video_file: string | null;
  aligned_video_file2: string | null;
  video_trim_status: string | null;
  trigger_count: number;
  started_at: string | null;
  first_trigger_at: string | null;
  elapsed_seconds: number;
  window_remaining_seconds: number | null;
  last_error: string | null;
  camera: HardwareStatus | null;
  camera2: HardwareStatus | null;
  daq: HardwareStatus | null;
  sync_timebase: string;
  t0_locked: boolean;
  expected_total_frames: number | null;
  video_t0_frame_estimated: number | null;
  usable_video_frame_start: number | null;
  usable_video_frame_end: number | null;
  preroll_seconds: number | null;
  stop_overshoot_samples: number | null;
  alignment_file: string | null;
  frame_map_file: string | null;
};

type TriggerRow = {
  trigger_index: number;
  absolute_time: string;
  relative_time_seconds: string;
  sample_number: number;
  frame_index: number;
  window_remaining: string;
  frame_mapping_mode: string;
  sample_offset_from_t0?: number;
  frame_index_from_t0?: number;
  video_frame_index_estimated?: number;
  timebase?: string;
};

type WaveformPayload = { sample_number: number; min: number; max: number; last: number; points: number[] };
type PreviewRotation = 0 | 90 | 180 | 270;
type AdjustTarget = "cam1" | "cam2" | "both";

/* ----------------------------- Backend ----------------------------- */
const backendUrl = window.mrc?.backendUrl ?? "http://127.0.0.1:7876";
const wsUrl = backendUrl.replace("http", "ws") + "/ws";

const status = ref<AppStatus | null>(null);
const triggers = ref<TriggerRow[]>([]);
const waveform = ref<number[]>([]);
const previewFrames = ref<[string, string]>(["", ""]);
const activePreviewIndex = ref(0);
const previewFrames2 = ref<[string, string]>(["", ""]);
const activePreviewIndex2 = ref(0);
const previewError = ref("");
const previewError2 = ref("");
const connection = ref("connecting");
const busy = ref(false);
const outputRoot = ref("runs");
const windowSeconds = ref(360);
const cameraFps = ref(30);
const cameraRotation = ref<PreviewRotation>(0);
const cameraRotation2 = ref<PreviewRotation>(0);
const thresholdVolts = ref(2.5);
const errorMessage = ref("");
const reconnectMessage = ref("");
const recordingMode = ref<"trigger" | "manual">("trigger");
let socket: WebSocket | null = null;
let reconnectTimer: number | null = null;
let reconnectMessageTimer: number | null = null;
let disposed = false;
let pendingPreviewSrc = "";
let pendingPreviewSrc2 = "";
let previewDecodeBusy = false;
let previewDecodeBusy2 = false;

/* --------------------- Image adjustment (new) --------------------- */
const adjust = reactive({ brightness: 100, contrast: 100, gamma: 100, saturation: 100, sharpness: 0 });
const adjustTarget = ref<AdjustTarget>("both");
const writeToVideo = ref(false);

/* 亮度/对比度/饱和度用 CSS filter；伽马/锐化 CSS 没有对应函数，
   用内联 SVG filter（feComponentTransfer gamma + feConvolveMatrix）补齐，
   预览五项全部实时生效。 */
const gammaExponent = computed(() => {
  const g = Math.min(2.6, Math.max(0.4, adjust.gamma / 100));
  return (1 / g).toFixed(4);
});
const sharpenKernel = computed(() => {
  const k = Math.min(1, Math.max(0, adjust.sharpness / 100)) * 0.8;
  const center = 1 + 4 * k;
  return `0 ${(-k).toFixed(3)} 0 ${(-k).toFixed(3)} ${center.toFixed(3)} ${(-k).toFixed(3)} 0 ${(-k).toFixed(3)} 0`;
});
const needsSvgFilter = computed(() => adjust.gamma !== 100 || adjust.sharpness > 0);
const cssFilterParts = computed(() => {
  const parts: string[] = [];
  if (adjust.brightness !== 100) parts.push(`brightness(${adjust.brightness / 100})`);
  if (adjust.contrast !== 100) parts.push(`contrast(${adjust.contrast / 100})`);
  if (adjust.saturation !== 100) parts.push(`saturate(${adjust.saturation / 100})`);
  if (needsSvgFilter.value) parts.push("url(#mrc-adjust-filter)");
  return parts;
});
const previewFilter1 = computed(() =>
  adjustTarget.value === "cam2" || !cssFilterParts.value.length ? "none" : cssFilterParts.value.join(" ")
);
const previewFilter2 = computed(() =>
  adjustTarget.value === "cam1" || !cssFilterParts.value.length ? "none" : cssFilterParts.value.join(" ")
);

const adjustControls = [
  { key: "brightness", label: "亮度 Brightness", min: 50, max: 150, step: 1, unit: "×" },
  { key: "contrast", label: "对比度 Contrast", min: 50, max: 150, step: 1, unit: "×" },
  { key: "gamma", label: "伽马 Gamma", min: 40, max: 260, step: 1, unit: "" },
  { key: "saturation", label: "饱和度 Saturation", min: 0, max: 200, step: 1, unit: "×" },
  { key: "sharpness", label: "锐化 Sharpness", min: 0, max: 100, step: 1, unit: "%" }
] as const;

function adjustDisplay(key: keyof typeof adjust) {
  const v = adjust[key];
  if (key === "sharpness") return `${v}%`;
  if (key === "gamma") return (v / 100).toFixed(2);
  return `${(v / 100).toFixed(2)}×`;
}

function resetAdjust() {
  adjust.brightness = 100;
  adjust.contrast = 100;
  adjust.gamma = 100;
  adjust.saturation = 100;
  adjust.sharpness = 0;
}

/** Push adjustment settings to the backend.
 *  writeToVideo=true 时后端把全部 5 项烘焙进输出视频（Trigger 模式写入
 *  对齐视频；手动模式停止后生成 *_adjusted 副本），原始录像始终保留。 */
async function pushImageAdjust() {
  try {
    await api("/image-adjust", {
      method: "POST",
      body: JSON.stringify({
        target: adjustTarget.value,
        write_to_video: writeToVideo.value,
        brightness: adjust.brightness / 100,
        contrast: adjust.contrast / 100,
        gamma: adjust.gamma / 100,
        saturation: adjust.saturation / 100,
        sharpness: adjust.sharpness / 100
      })
    });
  } catch {
    /* 后端未实现该端点时静默；预览仍实时生效 */
  }
}
let adjustPushTimer: number | null = null;
watch(
  [adjust, adjustTarget, writeToVideo],
  () => {
    if (adjustPushTimer !== null) window.clearTimeout(adjustPushTimer);
    adjustPushTimer = window.setTimeout(pushImageAdjust, 150);
  },
  { deep: true }
);

/* ----------------------- Scale-to-fill window ---------------------- */
const scaleRoot = ref<HTMLElement | null>(null);
const SCALE_BASE = 2133; // 2560 / 1.2  → 2560px 窗口下约 1.2× 放大
function applyScale() {
  const el = scaleRoot.value;
  if (!el) return;
  const s = window.innerWidth / SCALE_BASE;
  el.style.transform = `scale(${s})`;
  el.style.height = `${window.innerHeight / s}px`;
}

/* --------------------------- Computed ----------------------------- */
const canStart = computed(() => {
  const state = status.value?.state ?? "idle";
  return !busy.value && !["armed", "recording", "finalizing", "manual_recording"].includes(state);
});
const canStop = computed(() => {
  const state = status.value?.state ?? "idle";
  return !busy.value && ["armed", "recording", "manual_recording"].includes(state);
});
const isRecording = computed(() => {
  const state = status.value?.state ?? "idle";
  return ["armed", "recording", "manual_recording"].includes(state);
});
const stateLabel = computed(() => {
  const state = status.value?.state ?? "unknown";
  const labels: Record<string, string> = {
    idle: "待机", armed: "等待 Trigger", recording: "采集中", finalizing: "整理输出",
    manual_recording: "手动录制中", manual_stopped: "手动已停止", finished: "完成",
    stopped: "已停止", error: "错误"
  };
  return labels[state] ?? state;
});

function clock(sec: number, tenths: boolean) {
  const safe = Number.isFinite(sec) ? Math.max(0, sec) : 0;
  const m = Math.floor(safe / 60);
  const s = Math.floor(safe % 60);
  const base = `${m}:${String(s).padStart(2, "0")}`;
  return tenths ? `${base}.${Math.floor((safe % 1) * 10)}` : base;
}
const elapsedLabel = computed(() => clock(status.value?.elapsed_seconds ?? 0, true));
const remainLabel = computed(() =>
  status.value?.window_remaining_seconds == null ? "-" : clock(status.value.window_remaining_seconds, false)
);
const remainLow = computed(
  () => status.value?.window_remaining_seconds != null && status.value.window_remaining_seconds < 30
);
const t0Label = computed(() => (status.value?.t0_locked ? "已锁定" : "等待"));
const lastVolt = computed(() => (waveform.value.length ? waveform.value[waveform.value.length - 1] : 0));

const outputPath = computed(() => status.value?.output_dir ?? "-");
const cameraOnline = computed(() => Boolean(status.value?.camera?.initialized));
const camera2Online = computed(() => Boolean(status.value?.camera2?.initialized));
const daqOnline = computed(() => Boolean(status.value?.daq?.initialized));
const hasPreviewFrame = computed(() => previewFrames.value.some(Boolean));
const hasPreviewFrame2 = computed(() => previewFrames2.value.some(Boolean));
const effectiveCameraFps = computed(() => Number(status.value?.camera?.fps) || Number(cameraFps.value) || 30);
const sampleRateLabel = computed(() => {
  const hz = Number(status.value?.daq?.sample_rate_hz) || 0;
  return hz >= 1000 ? `${(hz / 1000).toFixed(0)} kHz` : `${hz} Hz`;
});
const triggerChannel = computed(() => status.value?.daq?.trigger_channel ?? 0);
/* 旋转适配：90°/270° 时舞台纵横比取倒数，图片盒子按舞台百分比换算
   （宽 = aspect×100%，高 = 100%/aspect），旋转后恰好铺满舞台——
   纯百分比数学，无偏移、无黑边。 */
const cam1Aspect = computed(() => {
  const w = Number(status.value?.camera?.width) || 720;
  const h = Number(status.value?.camera?.height) || 480;
  return w > 0 && h > 0 ? w / h : 1.5;
});
const cam2Aspect = computed(() => {
  const cam = status.value?.camera2 ?? status.value?.camera;
  const w = Number(cam?.width) || 720;
  const h = Number(cam?.height) || 480;
  return w > 0 && h > 0 ? w / h : 1.5;
});
function stageAspectStyle(aspect: number, rotation: PreviewRotation) {
  const quarter = rotation === 90 || rotation === 270;
  return { aspectRatio: String(quarter ? 1 / aspect : aspect) };
}
function rotatedImageStyle(aspect: number, rotation: PreviewRotation) {
  if (rotation === 90 || rotation === 270) {
    return {
      width: `${(aspect * 100).toFixed(4)}%`,
      height: `${(100 / aspect).toFixed(4)}%`,
      transform: `rotate(${rotation}deg)`
    };
  }
  return { transform: `rotate(${rotation}deg)` };
}
const videoStageStyle1 = computed(() => stageAspectStyle(cam1Aspect.value, cameraRotation.value));
const videoStageStyle2 = computed(() => stageAspectStyle(cam2Aspect.value, cameraRotation2.value));
const previewImageStyle = computed(() => rotatedImageStyle(cam1Aspect.value, cameraRotation.value));
const previewImageStyle2 = computed(() => rotatedImageStyle(cam2Aspect.value, cameraRotation2.value));

/* ------------------------------ API ------------------------------- */
async function api(path: string, init?: RequestInit, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${backendUrl}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
      signal: controller.signal
    });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  } catch (error) {
    if ((error as Error).name === "AbortError") throw new Error("请求超时，后端未响应");
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}
async function refreshStatus() {
  status.value = await api("/status");
}
async function initialize() {
  busy.value = true;
  errorMessage.value = "";
  try {
    status.value = await api("/initialize", { method: "POST" }, 120000);
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    busy.value = false;
  }
}
async function chooseOutputRoot() {
  if (!window.mrc?.selectOutputDirectory) {
    errorMessage.value = "当前运行环境不支持系统目录选择，请手动输入输出根目录。";
    return;
  }
  const selected = await window.mrc.selectOutputDirectory();
  if (selected) outputRoot.value = selected;
}
function validatePositiveNumbers(fields: Array<[string, unknown]>): boolean {
  for (const [label, value] of fields) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      errorMessage.value = `${label}必须是大于 0 的数字`;
      return false;
    }
  }
  return true;
}
async function startExperiment() {
  if (!validatePositiveNumbers([["采集窗口", windowSeconds.value], ["相机 FPS", cameraFps.value], ["Trigger 阈值", thresholdVolts.value]])) return;
  busy.value = true;
  errorMessage.value = "";
  triggers.value = [];
  try {
    status.value = await api("/experiment/start", {
      method: "POST",
      body: JSON.stringify({
        output_root: outputRoot.value,
        window_minutes: windowSeconds.value / 60,
        camera_fps: cameraFps.value,
        threshold_volts: thresholdVolts.value
      })
    });
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    busy.value = false;
  }
}
async function startManualRecording() {
  if (!validatePositiveNumbers([["相机 FPS", cameraFps.value]])) return;
  busy.value = true;
  errorMessage.value = "";
  triggers.value = [];
  try {
    status.value = await api("/manual-recording/start", {
      method: "POST",
      body: JSON.stringify({ output_root: outputRoot.value, camera_fps: cameraFps.value })
    });
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    busy.value = false;
  }
}
const canOpenLogs = Boolean(window.mrc?.openLogDirectory);
function openLogs() {
  window.mrc?.openLogDirectory?.().catch(() => {});
}
async function recoverCamera(cameraId: number) {
  busy.value = true;
  errorMessage.value = "";
  try {
    await api("/recover/camera", { method: "POST", body: JSON.stringify({ camera_id: cameraId }) }, 240000);
    if (cameraId === 2) previewError2.value = "";
    else previewError.value = "";
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    busy.value = false;
  }
}
async function stopExperiment() {
  busy.value = true;
  errorMessage.value = "";
  try {
    status.value = await api("/experiment/stop", { method: "POST" }, 60000);
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    busy.value = false;
  }
}

/* -------------------------- Preview decode ------------------------ */
async function queuePreviewFrame(src: string) {
  pendingPreviewSrc = src;
  if (previewDecodeBusy) return;
  await decodeLatestPreviewFrame();
}
async function queuePreviewFrame2(src: string) {
  pendingPreviewSrc2 = src;
  if (previewDecodeBusy2) return;
  await decodeLatestPreviewFrame2();
}
async function decodeLatestPreviewFrame() {
  while (pendingPreviewSrc) {
    const src = pendingPreviewSrc;
    pendingPreviewSrc = "";
    previewDecodeBusy = true;
    try {
      const image = new Image();
      image.decoding = "async";
      image.src = src;
      if (image.decode) await image.decode();
      else await new Promise<void>((resolve, reject) => { image.onload = () => resolve(); image.onerror = () => reject(new Error("preview image decode failed")); });
      const nextIndex = activePreviewIndex.value === 0 ? 1 : 0;
      previewFrames.value[nextIndex] = src;
      activePreviewIndex.value = nextIndex;
      previewError.value = "";
    } catch (error) {
      previewError.value = String(error);
    } finally {
      previewDecodeBusy = false;
    }
  }
}
async function decodeLatestPreviewFrame2() {
  while (pendingPreviewSrc2) {
    const src = pendingPreviewSrc2;
    pendingPreviewSrc2 = "";
    previewDecodeBusy2 = true;
    try {
      const image = new Image();
      image.decoding = "async";
      image.src = src;
      if (image.decode) await image.decode();
      else await new Promise<void>((resolve, reject) => { image.onload = () => resolve(); image.onerror = () => reject(new Error("preview image decode failed")); });
      const nextIndex = activePreviewIndex2.value === 0 ? 1 : 0;
      previewFrames2.value[nextIndex] = src;
      activePreviewIndex2.value = nextIndex;
      previewError2.value = "";
    } catch (error) {
      previewError2.value = String(error);
    } finally {
      previewDecodeBusy2 = false;
    }
  }
}

/* ------------------------------ Socket ---------------------------- */
function connectSocket() {
  if (disposed) return;
  socket?.close();
  socket = new WebSocket(wsUrl);
  socket.onopen = () => { connection.value = "online"; };
  socket.onclose = () => {
    connection.value = "offline";
    if (!disposed) reconnectTimer = window.setTimeout(connectSocket, 1500);
  };
  socket.onerror = () => { connection.value = "offline"; };
  socket.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === "status") status.value = event.payload;
    if (event.type === "trigger") triggers.value = [event.payload, ...triggers.value].slice(0, 200);
    if (event.type === "waveform") {
      const payload = event.payload as WaveformPayload;
      waveform.value = payload.points.slice(-120);
    }
    if (event.type === "preview") {
      if (event.payload.camera_id === 2) queuePreviewFrame2(event.payload.src);
      else queuePreviewFrame(event.payload.src);
    }
    if (event.type === "preview_error") {
      if (event.payload.camera_id === 2) previewError2.value = event.payload.message;
      else previewError.value = event.payload.message;
    }
    if (event.type === "reconnect") {
      const deviceLabels: Record<string, string> = { camera1: "相机1", camera2: "相机2", daq: "采集卡" };
      const device = deviceLabels[event.payload.device] ?? event.payload.device;
      if (reconnectMessageTimer !== null) { window.clearTimeout(reconnectMessageTimer); reconnectMessageTimer = null; }
      if (event.payload.status === "attempting") reconnectMessage.value = `${device}连接异常，正在自动重连…`;
      else if (event.payload.status === "ok") {
        reconnectMessage.value = `${device}重连成功`;
        reconnectMessageTimer = window.setTimeout(() => { reconnectMessage.value = ""; }, 5000);
      } else reconnectMessage.value = `${device}自动重连失败${event.payload.message ? `：${event.payload.message}` : ""}`;
    }
    if (event.type === "notice") {
      if (reconnectMessageTimer !== null) { window.clearTimeout(reconnectMessageTimer); reconnectMessageTimer = null; }
      reconnectMessage.value = String(event.payload.message ?? "");
      reconnectMessageTimer = window.setTimeout(() => { reconnectMessage.value = ""; }, 8000);
    }
    if (event.type === "error") errorMessage.value = event.payload.message;
  };
}

function sparklinePath(points: number[]) {
  if (!points.length) return "";
  const width = 560;
  const height = 84;
  const min = Math.min(...points, -0.1);
  const max = Math.max(...points, 5.1);
  return points
    .map((point, index) => {
      const x = (index / Math.max(1, points.length - 1)) * width;
      const y = height - ((point - min) / Math.max(0.001, max - min)) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}
const thresholdY = computed(() => {
  const min = -0.1;
  const max = 5.1;
  return (84 - ((thresholdVolts.value - min) / Math.max(0.001, max - min)) * 84).toFixed(1);
});

onMounted(() => {
  applyScale();
  window.addEventListener("resize", applyScale);
  refreshStatus().catch(() => { connection.value = "offline"; });
  // Adopt the backend's configured output root (packaged builds point it at
  // the user's Documents folder) unless the operator already changed it.
  api("/config")
    .then((cfg) => {
      if (outputRoot.value === "runs" && cfg?.output_root) outputRoot.value = String(cfg.output_root);
    })
    .catch(() => {});
  connectSocket();
});
onUnmounted(() => {
  disposed = true;
  window.removeEventListener("resize", applyScale);
  if (reconnectTimer !== null) { window.clearTimeout(reconnectTimer); reconnectTimer = null; }
  if (reconnectMessageTimer !== null) { window.clearTimeout(reconnectMessageTimer); reconnectMessageTimer = null; }
  if (adjustPushTimer !== null) { window.clearTimeout(adjustPushTimer); adjustPushTimer = null; }
  socket?.close();
});
</script>

<template>
  <div class="app-shell">
    <svg class="filter-defs" width="0" height="0" aria-hidden="true">
      <filter id="mrc-adjust-filter" color-interpolation-filters="sRGB">
        <feComponentTransfer>
          <feFuncR type="gamma" :exponent="gammaExponent" amplitude="1" offset="0" />
          <feFuncG type="gamma" :exponent="gammaExponent" amplitude="1" offset="0" />
          <feFuncB type="gamma" :exponent="gammaExponent" amplitude="1" offset="0" />
        </feComponentTransfer>
        <feConvolveMatrix
          v-if="adjust.sharpness > 0"
          order="3"
          :kernelMatrix="sharpenKernel"
          edgeMode="duplicate"
          preserveAlpha="true"
        />
      </filter>
    </svg>
    <div ref="scaleRoot" class="scale-root">
      <!-- Header -->
      <header class="app-header">
        <div class="brand">
          <div class="brand-logo">M</div>
          <span class="brand-title">MRC 双机采集控制台</span>
        </div>
        <div class="header-chips">
          <div class="chip">
            <i class="dot" :class="isRecording ? 'rec' : 'idle'"></i>{{ stateLabel }}
          </div>
          <div class="chip mono">{{ status?.sync_timebase ?? "daq_sample_clock" }}</div>
          <div class="chip">
            <i class="dot" :class="connection === 'online' ? 'ok' : 'off'"></i>
            {{ connection === "online" ? "在线" : "离线" }}
          </div>
          <button v-if="canOpenLogs" class="chip chip-btn" title="打开日志文件夹" @click="openLogs">
            <FileText :size="13" />日志
          </button>
        </div>
      </header>

      <!-- Video row -->
      <div class="video-row">
        <section class="panel">
          <div class="panel-head">
            <span class="panel-title"><i class="status-dot" :class="cameraOnline ? 'online' : 'offline'"></i>原始视频 · 1号</span>
            <span class="head-actions">
              <button
                v-if="previewError || !cameraOnline"
                class="fix-btn"
                :disabled="busy || isRecording"
                title="自动修复相机（重连，必要时复位设备）"
                @click="recoverCamera(1)"
              >
                <Wrench :size="12" />修复
              </button>
              <small class="rec-pill" :class="{ live: !status?.camera?.recording }">{{ status?.camera?.recording ? "REC" : "LIVE" }}</small>
            </span>
          </div>
          <div class="video-body">
            <div class="video-stage" :style="[{ filter: previewFilter1 }, videoStageStyle1]">
              <img
                v-for="(frame, index) in previewFrames"
                v-show="frame"
                :key="index"
                :src="frame"
                alt="Camera 1 preview"
                class="preview-image"
                :class="{ active: index === activePreviewIndex }"
                :style="previewImageStyle"
                decoding="async"
              />
              <div v-if="!hasPreviewFrame" class="video-empty">等待相机初始化</div>
              <div v-else class="video-meta">CAMERA 1 · {{ effectiveCameraFps.toFixed(0) }} fps · 旋转 {{ cameraRotation }}°</div>
              <span v-if="previewError" class="preview-error">{{ previewError }}</span>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <span class="panel-title"><i class="status-dot" :class="camera2Online ? 'online' : 'offline'"></i>原始视频 · 2号</span>
            <span class="head-actions">
              <button
                v-if="status?.camera2 && (previewError2 || !camera2Online)"
                class="fix-btn"
                :disabled="busy || isRecording"
                title="自动修复相机（重连，必要时复位设备）"
                @click="recoverCamera(2)"
              >
                <Wrench :size="12" />修复
              </button>
              <small class="rec-pill" :class="{ live: !status?.camera2?.recording }">
                {{ status?.camera2?.recording ? "REC" : status?.camera2?.initialized ? "LIVE" : "OFF" }}
              </small>
            </span>
          </div>
          <div class="video-body">
            <div class="video-stage" :style="[{ filter: previewFilter2 }, videoStageStyle2]">
              <img
                v-for="(frame, index) in previewFrames2"
                v-show="frame"
                :key="index"
                :src="frame"
                alt="Camera 2 preview"
                class="preview-image"
                :class="{ active: index === activePreviewIndex2 }"
                :style="previewImageStyle2"
                decoding="async"
              />
              <div v-if="!hasPreviewFrame2" class="video-empty">{{ status?.camera2 ? "等待二号相机初始化" : "二号相机未启用" }}</div>
              <div v-else class="video-meta">CAMERA 2 · {{ effectiveCameraFps.toFixed(0) }} fps · 旋转 {{ cameraRotation2 }}°</div>
              <span v-if="previewError2" class="preview-error">{{ previewError2 }}</span>
            </div>
          </div>
        </section>
      </div>

      <!-- Bottom row -->
      <div class="bottom-row">
        <!-- Trigger + settings -->
        <section class="panel">
          <div class="panel-head">
            <span class="panel-title"><i class="status-dot" :class="daqOnline ? 'online' : 'offline'"></i>Trigger · 采集设置</span>
            <div class="device-row">
              <span><i class="dot ok"></i>相机1</span>
              <span><i class="dot" :class="camera2Online ? 'ok' : 'off'"></i>相机2</span>
              <span><i class="dot" :class="daqOnline ? 'ok' : 'off'"></i>USB3000</span>
              <span class="mono">AI{{ triggerChannel }}·{{ sampleRateLabel }}</span>
            </div>
          </div>

          <div class="trigger-body">
            <!-- left: trigger readouts -->
            <div class="trig-left">
              <section v-if="errorMessage || status?.last_error" class="alert">
                <AlertTriangle :size="16" /><span>{{ errorMessage || status?.last_error }}</span>
              </section>
              <section v-else-if="reconnectMessage" class="alert reconnect">
                <RotateCw :size="16" /><span>{{ reconnectMessage }}</span>
              </section>

              <div class="stat-grid">
                <div class="stat-card"><span>已录制时间</span><strong class="tnum">{{ elapsedLabel }}</strong></div>
                <div class="stat-card"><span>剩余时间</span><strong class="tnum" :class="{ warn: remainLow }">{{ remainLabel }}</strong></div>
                <div class="stat-card"><span>Trigger 接受</span><strong class="tnum accent">{{ status?.trigger_count ?? 0 }}</strong></div>
                <div class="stat-card"><span>T0 状态</span><strong>{{ t0Label }}</strong></div>
              </div>

              <div class="wave-wrap">
                <div class="wave-head">
                  <span>当前信号流图</span>
                  <span class="mono tnum">阈值 {{ thresholdVolts.toFixed(1) }} V · 实时 {{ lastVolt.toFixed(2) }} V</span>
                </div>
                <div class="wave-box">
                  <svg class="waveform" viewBox="0 0 560 84" preserveAspectRatio="none">
                    <line class="threshold" :x1="0" :y1="thresholdY" :x2="560" :y2="thresholdY" />
                    <path class="trace" :d="sparklinePath(waveform)" />
                  </svg>
                </div>
              </div>

              <div class="trig-table">
                <div class="trig-thead"><span>#</span><span>rel s</span><span>sample</span><span class="right">状态</span></div>
                <div class="trig-tbody">
                  <div v-for="trigger in triggers" :key="trigger.trigger_index" class="trig-trow">
                    <span class="tnum dim">{{ trigger.trigger_index }}</span>
                    <span class="tnum">{{ trigger.relative_time_seconds }}</span>
                    <span class="tnum mono">{{ trigger.sample_number }}</span>
                    <span class="trig-pill">接受</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- right: controls + params -->
            <div class="settings-col">
              <div class="seg">
                <button class="seg-btn" :class="{ active: recordingMode === 'trigger' }" :disabled="!canStart" @click="recordingMode = 'trigger'">Trigger 录制</button>
                <button class="seg-btn" :class="{ active: recordingMode === 'manual' }" :disabled="!canStart" @click="recordingMode = 'manual'">手动录制</button>
              </div>

              <div class="actions">
                <button class="btn btn-ghost" :disabled="!canStart" @click="initialize">初始化</button>
                <button v-if="recordingMode === 'trigger'" class="btn btn-primary" :disabled="!canStart" @click="startExperiment"><Play :size="15" />开始</button>
                <button v-else class="btn btn-primary" :disabled="!canStart" @click="startManualRecording"><Play :size="15" />手动</button>
                <button class="btn btn-danger" :disabled="!canStop" @click="stopExperiment"><Square :size="14" />停止</button>
              </div>

              <div class="param-grid">
                <label class="field wide">
                  <span>输出根目录</span>
                  <div class="path-picker">
                    <input v-model="outputRoot" />
                    <button type="button" :disabled="busy || !canStart" @click="chooseOutputRoot"><FolderOpen :size="14" />选择</button>
                  </div>
                  <small class="path-hint">{{ outputPath }}</small>
                </label>
                <label class="field"><span>采集窗口 (s)</span><input v-model.number="windowSeconds" type="number" min="1" step="1" /></label>
                <label class="field"><span>相机 FPS</span><input v-model.number="cameraFps" type="number" min="1" step="0.1" :disabled="!canStart" /></label>
                <label class="field"><span>Trigger 阈值 (V)</span><input v-model.number="thresholdVolts" type="number" min="0" step="0.1" /></label>
                <div class="field-pair">
                  <label class="field"><span>视频1旋转</span>
                    <select v-model.number="cameraRotation"><option :value="0">0°</option><option :value="90">90°</option><option :value="180">180°</option><option :value="270">270°</option></select>
                  </label>
                  <label class="field"><span>视频2旋转</span>
                    <select v-model.number="cameraRotation2"><option :value="0">0°</option><option :value="90">90°</option><option :value="180">180°</option><option :value="270">270°</option></select>
                  </label>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Real-time image adjustment -->
        <section class="panel">
          <div class="panel-head">
            <span class="panel-title"><SlidersHorizontal :size="16" class="title-icon" />实时图像调整</span>
            <small class="head-sub">预览即时生效</small>
          </div>
          <div class="adjust-body">
            <div class="target-block">
              <span class="field-label">应用目标</span>
              <div class="target-seg">
                <button class="seg-btn" :class="{ active: adjustTarget === 'cam1' }" @click="adjustTarget = 'cam1'">相机 1</button>
                <button class="seg-btn" :class="{ active: adjustTarget === 'cam2' }" @click="adjustTarget = 'cam2'">相机 2</button>
                <button class="seg-btn" :class="{ active: adjustTarget === 'both' }" @click="adjustTarget = 'both'">双相机</button>
              </div>
            </div>

            <div class="slider-list">
              <div v-for="ctrl in adjustControls" :key="ctrl.key" class="slider-row">
                <div class="slider-head">
                  <span>{{ ctrl.label }}</span>
                  <span class="mono tnum">{{ adjustDisplay(ctrl.key as keyof typeof adjust) }}</span>
                </div>
                <input
                  class="range"
                  type="range"
                  :min="ctrl.min"
                  :max="ctrl.max"
                  :step="ctrl.step"
                  v-model.number="adjust[ctrl.key as keyof typeof adjust]"
                />
              </div>
            </div>

            <div class="adjust-foot">
              <button class="write-toggle" :class="{ on: writeToVideo }" @click="writeToVideo = !writeToVideo">
                <span class="wt-label"><Save :size="15" />应用到写盘视频</span>
                <span class="wt-pill">{{ writeToVideo ? "写入" : "仅预览" }}</span>
              </button>
              <button class="btn btn-ghost full" @click="resetAdjust"><RotateCw :size="15" />恢复默认</button>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
