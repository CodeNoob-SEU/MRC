# Bundled FFmpeg Runtime

Windows setup scripts install a local FFmpeg runtime here:

```text
vendor/ffmpeg/windows/bin/ffmpeg.exe
vendor/ffmpeg/windows/bin/ffprobe.exe
```

The binaries are downloaded by `scripts/setup_ffmpeg_windows.ps1` from the Windows essentials build hosted by gyan.dev. They are not committed to this repository because the archive is large and changes over time.

The backend automatically prefers this bundled executable for post-trigger video trimming. If it is missing, the backend falls back to `MRC_FFMPEG` and then `ffmpeg` from `PATH`.
