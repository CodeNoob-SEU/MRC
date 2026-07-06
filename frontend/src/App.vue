<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { Activity, FolderOpen, Play, RotateCw, Square, Usb, Video, AlertTriangle } from "lucide-vue-next";

type HardwareStatus = {
  mode: string;
  initialized: boolean;
  recording?: boolean;
  sampling?: boolean;
  device_count?: number;
  device_name?: string;
  sample_rate_hz?: number;
  trigger_channel?: number;
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

type WaveformPayload = {
  sample_number: number;
  min: number;
  max: number;
  last: number;
  points: number[];
};

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
const windowMinutes = ref(6);
const cameraFps = ref(30);
const thresholdVolts = ref(2.5);
const errorMessage = ref("");
const recordingMode = ref<"trigger" | "manual">("trigger");
let socket: WebSocket | null = null;
let pendingPreviewSrc = "";
let pendingPreviewSrc2 = "";
let previewDecodeBusy = false;
let previewDecodeBusy2 = false;

const canStart = computed(() => {
  const state = status.value?.state ?? "idle";
  return !busy.value && !["armed", "recording", "finalizing", "manual_recording"].includes(state);
});

const canStop = computed(() => {
  const state = status.value?.state ?? "idle";
  return !busy.value && ["armed", "recording", "manual_recording"].includes(state);
});

const stateLabel = computed(() => {
  const state = status.value?.state ?? "unknown";
  const labels: Record<string, string> = {
    idle: "待机",
    armed: "等待 Trigger",
    recording: "采集中",
    finalizing: "整理输出",
    manual_recording: "手动录制中",
    manual_stopped: "手动已停止",
    finished: "完成",
    stopped: "已停止",
    error: "错误"
  };
  return labels[state] ?? state;
});

const effectiveFrameRange = computed(() => {
  if (status.value?.usable_video_frame_start == null || status.value.usable_video_frame_end == null) {
    return "-";
  }
  return `${status.value.usable_video_frame_start}-${status.value.usable_video_frame_end}`;
});

const prerollLabel = computed(() => {
  if (status.value?.preroll_seconds == null) {
    return "-";
  }
  return `${status.value.preroll_seconds.toFixed(3)} s`;
});

const remainingWindowLabel = computed(() => {
  if (status.value?.window_remaining_seconds == null) {
    return "-";
  }
  return `${status.value.window_remaining_seconds.toFixed(1)} s`;
});

const outputPath = computed(() => status.value?.output_dir ?? "-");
const cameraOnline = computed(() => Boolean(status.value?.camera?.initialized));
const camera2Online = computed(() => Boolean(status.value?.camera2?.initialized));
const daqOnline = computed(() => Boolean(status.value?.daq?.initialized));
const hasPreviewFrame = computed(() => previewFrames.value.some(Boolean));
const hasPreviewFrame2 = computed(() => previewFrames2.value.some(Boolean));
const effectiveCameraFps = computed(() => status.value?.camera?.fps || cameraFps.value);
const trimStatusLabel = computed(() => {
  if (status.value?.aligned_video_file) {
    return "裁剪完成";
  }
  if (status.value?.video_trim_status) {
    return `裁剪: ${status.value.video_trim_status}`;
  }
  return status.value?.camera?.preview_status || status.value?.camera?.capture_status || "等待硬件状态";
});

async function api(path: string, init?: RequestInit) {
  const response = await fetch(`${backendUrl}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function refreshStatus() {
  status.value = await api("/status");
}

async function initialize() {
  busy.value = true;
  errorMessage.value = "";
  try {
    status.value = await api("/initialize", { method: "POST" });
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
  if (selected) {
    outputRoot.value = selected;
  }
}

async function startExperiment() {
  busy.value = true;
  errorMessage.value = "";
  triggers.value = [];
  try {
    status.value = await api("/experiment/start", {
      method: "POST",
      body: JSON.stringify({
        output_root: outputRoot.value,
        window_minutes: windowMinutes.value,
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
  busy.value = true;
  errorMessage.value = "";
  triggers.value = [];
  try {
    status.value = await api("/manual-recording/start", {
      method: "POST",
      body: JSON.stringify({
        output_root: outputRoot.value,
        camera_fps: cameraFps.value
      })
    });
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
    status.value = await api("/experiment/stop", { method: "POST" });
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    busy.value = false;
  }
}

async function queuePreviewFrame(src: string) {
  pendingPreviewSrc = src;
  if (previewDecodeBusy) {
    return;
  }
  await decodeLatestPreviewFrame();
}

async function queuePreviewFrame2(src: string) {
  pendingPreviewSrc2 = src;
  if (previewDecodeBusy2) {
    return;
  }
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
      if (image.decode) {
        await image.decode();
      } else {
        await new Promise<void>((resolve, reject) => {
          image.onload = () => resolve();
          image.onerror = () => reject(new Error("preview image decode failed"));
        });
      }
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
      if (image.decode) {
        await image.decode();
      } else {
        await new Promise<void>((resolve, reject) => {
          image.onload = () => resolve();
          image.onerror = () => reject(new Error("preview image decode failed"));
        });
      }
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

function connectSocket() {
  socket?.close();
  socket = new WebSocket(wsUrl);
  socket.onopen = () => {
    connection.value = "online";
  };
  socket.onclose = () => {
    connection.value = "offline";
    window.setTimeout(connectSocket, 1500);
  };
  socket.onerror = () => {
    connection.value = "offline";
  };
  socket.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === "status") {
      status.value = event.payload;
    }
    if (event.type === "trigger") {
      triggers.value = [event.payload, ...triggers.value].slice(0, 200);
    }
    if (event.type === "waveform") {
      const payload = event.payload as WaveformPayload;
      waveform.value = payload.points.slice(-120);
    }
    if (event.type === "preview") {
      if (event.payload.camera_id === 2) {
        queuePreviewFrame2(event.payload.src);
      } else {
        queuePreviewFrame(event.payload.src);
      }
    }
    if (event.type === "preview_error") {
      if (event.payload.camera_id === 2) {
        previewError2.value = event.payload.message;
      } else {
        previewError.value = event.payload.message;
      }
    }
    if (event.type === "error") {
      errorMessage.value = event.payload.message;
    }
  };
}

function sparklinePath(points: number[]) {
  if (!points.length) {
    return "";
  }
  const width = 560;
  const height = 96;
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

onMounted(() => {
  refreshStatus().catch(() => {
    connection.value = "offline";
  });
  connectSocket();
});

onUnmounted(() => {
  socket?.close();
});
</script>

<template>
  <main class="shell">
    <section class="lab-layout">
      <section class="lab-panel video-panel">
        <div class="panel-title">
          <span class="title-label">
            <i class="status-dot" :class="cameraOnline ? 'online' : 'offline'" aria-hidden="true"></i>
            原始视频1号
          </span>
          <small>{{ status?.camera?.recording ? "REC" : "LIVE" }}</small>
        </div>
        <div class="video-stage">
          <img
            v-for="(frame, index) in previewFrames"
            v-show="frame"
            :key="index"
            :src="frame"
            alt="Camera preview"
            class="preview-image"
            :class="{ active: index === activePreviewIndex }"
            decoding="async"
          />
          <div v-if="!hasPreviewFrame" class="video-empty">等待相机初始化</div>
          <span v-if="previewError" class="preview-error">{{ previewError }}</span>
        </div>
      </section>

      <section class="lab-panel video-panel">
        <div class="panel-title">
          <span class="title-label">
            <i class="status-dot" :class="camera2Online ? 'online' : 'offline'" aria-hidden="true"></i>
            原始视频2号
          </span>
          <small>{{ status?.camera2?.recording ? "REC" : status?.camera2?.initialized ? "LIVE" : "disabled" }}</small>
        </div>
        <div class="video-stage" :class="{ 'video-placeholder': !status?.camera2 }">
          <img
            v-for="(frame, index) in previewFrames2"
            v-show="frame"
            :key="index"
            :src="frame"
            alt="Camera 2 preview"
            class="preview-image"
            :class="{ active: index === activePreviewIndex2 }"
            decoding="async"
          />
          <div v-if="!hasPreviewFrame2" class="video-empty">
            {{ status?.camera2 ? "等待二号相机初始化" : "二号相机未启用" }}
          </div>
          <span v-if="previewError2" class="preview-error">{{ previewError2 }}</span>
        </div>
      </section>

      <section class="lab-panel trigger-panel">
        <div class="panel-title">
          <span class="title-label">
            <i class="status-dot" :class="daqOnline ? 'online' : 'offline'" aria-hidden="true"></i>
            Trigger
          </span>
          <small>{{ status?.sync_timebase ?? "daq_sample_clock" }}</small>
        </div>
        <div class="trigger-metrics">
          <div>
            <span>Trigger</span>
            <strong>{{ status?.trigger_count ?? 0 }}</strong>
          </div>
          <div>
            <span>rel time</span>
            <strong>{{ (status?.elapsed_seconds ?? 0).toFixed(3) }} s</strong>
          </div>
          <div>
            <span>remaining</span>
            <strong>{{ remainingWindowLabel }}</strong>
          </div>
          <div>
            <span>t0</span>
            <strong>{{ status?.t0_locked ? "locked" : "waiting" }}</strong>
          </div>
        </div>
        <svg class="waveform" viewBox="0 0 560 96" preserveAspectRatio="none">
          <path class="threshold" d="M 0 48 L 560 48" />
          <path class="trace" :d="sparklinePath(waveform)" />
        </svg>
        <div class="trigger-table">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>rel s</th>
                <th>sample</th>
                <th>t0 frame</th>
                <th>video frame</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="trigger in triggers" :key="trigger.trigger_index">
                <td>{{ trigger.trigger_index }}</td>
                <td>{{ trigger.relative_time_seconds }}</td>
                <td>{{ trigger.sample_number }}</td>
                <td>{{ trigger.frame_index_from_t0 ?? trigger.frame_index }}</td>
                <td>{{ trigger.video_frame_index_estimated ?? "-" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="lab-panel control-panel">
        <div class="panel-title">
          <span>参数设置 / 系统状态 / 开关</span>
          <small>{{ recordingMode === "trigger" ? "Trigger模式" : "手动模式" }} · {{ stateLabel }} · {{ connection }}</small>
        </div>

        <section v-if="errorMessage || status?.last_error" class="alert">
          <AlertTriangle :size="17" />
          <span>{{ errorMessage || status?.last_error }}</span>
        </section>

        <div class="mode-toggle">
          <span>录制模式</span>
          <div>
            <button
              :class="{ active: recordingMode === 'trigger' }"
              :disabled="!canStart"
              @click="recordingMode = 'trigger'"
            >
              Trigger录制
            </button>
            <button
              :class="{ active: recordingMode === 'manual' }"
              :disabled="!canStart"
              @click="recordingMode = 'manual'"
            >
              手动录制
            </button>
          </div>
        </div>

        <div class="control-actions">
          <button class="secondary" :disabled="busy" @click="initialize">
            <RotateCw :size="17" />
            初始化
          </button>
          <button
            v-if="recordingMode === 'trigger'"
            class="primary"
            :disabled="!canStart"
            @click="startExperiment"
          >
            <Play :size="17" />
            开始Trigger
          </button>
          <button
            v-else
            class="primary"
            :disabled="!canStart"
            @click="startManualRecording"
          >
            <Play :size="17" />
            手动录制
          </button>
          <button class="danger" :disabled="!canStop" @click="stopExperiment">
            <Square :size="17" />
            停止
          </button>
        </div>

        <div class="control-body">
          <div class="control-column params-column">
            <div class="subsection-title">参数</div>
            <div class="form-grid">
              <label class="output-root-field">
                <span>输出根目录</span>
                <div class="path-picker">
                  <input v-model="outputRoot" />
                  <button type="button" :disabled="busy || !canStart" title="选择输出根目录" @click="chooseOutputRoot">
                    <FolderOpen :size="16" />
                    选择
                  </button>
                </div>
                <small>输出目录：{{ outputPath }}</small>
              </label>
              <label>
                <span>采集窗口 min</span>
                <input v-model.number="windowMinutes" type="number" min="0.01" step="0.01" />
              </label>
              <label>
                <span>相机 FPS · 当前 {{ effectiveCameraFps.toFixed(1) }}</span>
                <input v-model.number="cameraFps" type="number" min="1" step="0.1" :disabled="!canStart" />
              </label>
              <label>
                <span>Trigger 阈值 V</span>
                <input v-model.number="thresholdVolts" type="number" min="0" step="0.1" />
              </label>
            </div>
          </div>

          <div class="control-column state-column">
            <div class="subsection-title">状态</div>
            <div class="status-grid">
              <div class="status-card">
                <Video :size="18" />
                <span>Camera 1</span>
                <strong>{{ status?.camera?.mode ?? "-" }} · {{ status?.camera?.recording ? "recording" : "idle" }}</strong>
                <small>{{ status?.camera?.device_name ?? "No device name" }}</small>
              </div>
              <div class="status-card">
                <Video :size="18" />
                <span>Camera 2</span>
                <strong>{{ status?.camera2?.mode ?? "-" }} · {{ status?.camera2?.recording ? "recording" : "idle" }}</strong>
                <small>{{ status?.camera2?.device_name ?? "未启用" }}</small>
              </div>
              <div class="status-card">
                <Usb :size="18" />
                <span>USB3000</span>
                <strong>{{ status?.daq?.mode ?? "-" }} · {{ status?.daq?.sampling ? "sampling" : "idle" }}</strong>
                <small>{{ status?.daq?.sample_rate_hz ?? 0 }} Hz · AI{{ status?.daq?.trigger_channel ?? 0 }}</small>
              </div>
            </div>

            <div class="sync-grid">
              <div>
                <span>预计总帧数</span>
                <strong>{{ status?.expected_total_frames ?? "-" }}</strong>
              </div>
              <div>
                <span>有效视频帧</span>
                <strong>{{ effectiveFrameRange }}</strong>
              </div>
              <div>
                <span>预录时长</span>
                <strong>{{ prerollLabel }}</strong>
              </div>
              <div>
                <span>停止 overshoot</span>
                <strong>{{ status?.stop_overshoot_samples ?? "-" }}</strong>
              </div>
            </div>

            <div class="sdk-log">
              <Activity :size="17" />
              <span>{{ trimStatusLabel }}</span>
            </div>
          </div>
        </div>
      </section>
    </section>
  </main>
</template>
