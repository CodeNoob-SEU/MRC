<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { Play, RotateCw, Square, Usb, Video, AlertTriangle } from "lucide-vue-next";

type HardwareStatus = {
  mode: string;
  initialized: boolean;
  recording?: boolean;
  sampling?: boolean;
  device_count?: number;
  device_name?: string;
  sample_rate_hz?: number;
  trigger_channel?: number;
  active_file?: string | null;
  capture_status?: string;
  video_source_status?: string;
  preview_status?: string;
  preview_started?: boolean;
};

type AppStatus = {
  state: string;
  session_id: string | null;
  output_dir: string | null;
  video_file: string | null;
  trigger_count: number;
  started_at: string | null;
  first_trigger_at: string | null;
  elapsed_seconds: number;
  window_remaining_seconds: number | null;
  last_error: string | null;
  camera: HardwareStatus | null;
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
const previewSrc = ref("");
const previewError = ref("");
const connection = ref("connecting");
const busy = ref(false);
const outputRoot = ref("runs");
const windowMinutes = ref(6);
const cameraFps = ref(30);
const thresholdVolts = ref(2.5);
const errorMessage = ref("");
let socket: WebSocket | null = null;

const canStart = computed(() => {
  const state = status.value?.state ?? "idle";
  return !busy.value && !["armed", "recording"].includes(state);
});

const canStop = computed(() => {
  const state = status.value?.state ?? "idle";
  return !busy.value && ["armed", "recording"].includes(state);
});

const stateLabel = computed(() => {
  const state = status.value?.state ?? "unknown";
  const labels: Record<string, string> = {
    idle: "待机",
    armed: "等待 Trigger",
    recording: "采集中",
    finished: "完成",
    stopped: "已停止",
    error: "错误"
  };
  return labels[state] ?? state;
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
      previewSrc.value = event.payload.src;
      previewError.value = "";
    }
    if (event.type === "preview_error") {
      previewError.value = event.payload.message;
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
    <header class="topbar">
      <div>
        <h1>MRC Integrated Acquisition</h1>
        <p>{{ stateLabel }} · {{ connection }}</p>
      </div>
      <div class="toolbar">
        <button class="secondary" :disabled="busy" @click="initialize">
          <RotateCw :size="17" />
          初始化
        </button>
        <button class="primary" :disabled="!canStart" @click="startExperiment">
          <Play :size="17" />
          开始
        </button>
        <button class="danger" :disabled="!canStop" @click="stopExperiment">
          <Square :size="17" />
          停止
        </button>
      </div>
    </header>

    <section v-if="errorMessage || status?.last_error" class="alert">
      <AlertTriangle :size="18" />
      <span>{{ errorMessage || status?.last_error }}</span>
    </section>

    <section class="overview">
      <div class="metric">
        <span>Trigger</span>
        <strong>{{ status?.trigger_count ?? 0 }}</strong>
      </div>
      <div class="metric">
        <span>相对时间</span>
        <strong>{{ (status?.elapsed_seconds ?? 0).toFixed(3) }} s</strong>
      </div>
      <div class="metric">
        <span>剩余窗口</span>
        <strong>{{ status?.window_remaining_seconds == null ? "-" : status.window_remaining_seconds.toFixed(1) + " s" }}</strong>
      </div>
      <div class="metric">
        <span>同步 t0</span>
        <strong>{{ status?.t0_locked ? "locked" : "waiting" }}</strong>
      </div>
      <div class="metric">
        <span>预计总帧数</span>
        <strong>{{ status?.expected_total_frames ?? "-" }}</strong>
      </div>
      <div class="metric">
        <span>有效视频帧</span>
        <strong>{{ status?.usable_video_frame_start == null ? "-" : status.usable_video_frame_start + "-" + status?.usable_video_frame_end }}</strong>
      </div>
      <div class="metric">
        <span>预录时长</span>
        <strong>{{ status?.preroll_seconds == null ? "-" : status.preroll_seconds.toFixed(3) + " s" }}</strong>
      </div>
      <div class="metric wide">
        <span>输出目录</span>
        <strong>{{ status?.output_dir ?? "-" }}</strong>
      </div>
    </section>

    <section class="workspace">
      <div class="left">
        <section class="panel">
          <h2>相机实时画面</h2>
          <div class="preview">
            <img v-if="previewSrc" :src="previewSrc" alt="Camera preview" />
            <div v-else class="preview-empty">等待相机初始化</div>
            <span v-if="previewError" class="preview-error">{{ previewError }}</span>
          </div>
        </section>

        <section class="panel">
          <h2>实验参数</h2>
          <div class="form-grid">
            <label>
              <span>输出根目录</span>
              <input v-model="outputRoot" />
            </label>
            <label>
              <span>采集窗口 min</span>
              <input v-model.number="windowMinutes" type="number" min="0.01" step="0.01" />
            </label>
            <label>
              <span>相机 FPS</span>
              <input v-model.number="cameraFps" type="number" min="1" step="0.1" />
            </label>
            <label>
              <span>Trigger 阈值 V</span>
              <input v-model.number="thresholdVolts" type="number" min="0" step="0.1" />
            </label>
          </div>
        </section>

        <section class="panel">
          <h2>Trigger 波形</h2>
          <svg class="waveform" viewBox="0 0 560 96" preserveAspectRatio="none">
            <path class="threshold" d="M 0 48 L 560 48" />
            <path class="trace" :d="sparklinePath(waveform)" />
          </svg>
        </section>

        <section class="panel">
          <h2>硬件状态</h2>
          <div class="hardware">
            <div>
              <Video :size="20" />
              <span>Camera</span>
              <strong>{{ status?.camera?.mode ?? "-" }} · {{ status?.camera?.recording ? "recording" : "idle" }}</strong>
              <small>{{ status?.camera?.device_name ?? "No device name" }}</small>
              <small v-if="status?.camera?.preview_status">{{ status.camera.preview_status }}</small>
              <small v-if="status?.camera?.capture_status">{{ status.camera.capture_status }}</small>
            </div>
            <div>
              <Usb :size="20" />
              <span>USB3000</span>
              <strong>{{ status?.daq?.mode ?? "-" }} · {{ status?.daq?.sampling ? "sampling" : "idle" }}</strong>
              <small>{{ status?.daq?.sample_rate_hz ?? 0 }} Hz · AI{{ status?.daq?.trigger_channel ?? 0 }}</small>
            </div>
          </div>
        </section>
      </div>

      <section class="panel table-panel">
        <h2>Trigger 事件</h2>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>时间</th>
              <th>rel s</th>
              <th>sample</th>
              <th>t0 frame</th>
              <th>video frame</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="trigger in triggers" :key="trigger.trigger_index">
              <td>{{ trigger.trigger_index }}</td>
              <td>{{ trigger.absolute_time }}</td>
              <td>{{ trigger.relative_time_seconds }}</td>
              <td>{{ trigger.sample_number }}</td>
              <td>{{ trigger.frame_index_from_t0 ?? trigger.frame_index }}</td>
              <td>{{ trigger.video_frame_index_estimated ?? "-" }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </section>
  </main>
</template>
