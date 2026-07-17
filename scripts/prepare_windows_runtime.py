from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile


PYTHON_VERSION = "3.10.11"
PYTHON_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-win32.zip"
)
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    runtime_dir = repo_root / "frontend" / "build" / "python-win32"
    site_packages = runtime_dir / "Lib" / "site-packages"

    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="mrc-python-win32-") as temporary:
        archive = Path(temporary) / "python-embed-win32.zip"
        print(f"Downloading {PYTHON_URL}")
        urllib.request.urlretrieve(PYTHON_URL, archive)
        with zipfile.ZipFile(archive) as source:
            source.extractall(runtime_dir)

    pth_file = runtime_dir / "python310._pth"
    pth_file.write_text(
        "python310.zip\n.\nLib\\site-packages\nimport site\n",
        encoding="utf-8",
    )
    site_packages.mkdir(parents=True)

    source_requirements = repo_root / "backend" / "requirements.txt"
    runtime_requirements = runtime_dir / "requirements.txt"
    # uvicorn[standard] pulls compiled extras that lack win32 wheels; plain
    # uvicorn works but needs an explicit websocket library or /ws breaks.
    runtime_requirements.write_text(
        source_requirements.read_text(encoding="utf-8").replace(
            "uvicorn[standard]",
            "uvicorn",
        )
        + "websockets>=12,<15\n",
        encoding="utf-8",
    )
    run(
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--target",
        str(site_packages),
        "--platform",
        "win32",
        "--python-version",
        "3.10",
        "--implementation",
        "cp",
        "--abi",
        "cp310",
        "--only-binary=:all:",
        "-r",
        str(runtime_requirements),
    )
    runtime_requirements.unlink()

    for directory in site_packages.rglob("__pycache__"):
        shutil.rmtree(directory)
    print(f"Prepared Windows x86 Python runtime at {runtime_dir}")

    ffmpeg_dir = repo_root / "vendor" / "ffmpeg" / "windows" / "bin"
    ffmpeg_targets = [ffmpeg_dir / "ffmpeg.exe", ffmpeg_dir / "ffprobe.exe"]
    if not all(target.exists() for target in ffmpeg_targets):
        download_dir = repo_root / ".download"
        archive = download_dir / "ffmpeg-release-essentials.zip"
        download_dir.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            print(f"Downloading {FFMPEG_URL}")
            urllib.request.urlretrieve(FFMPEG_URL, archive)
        with tempfile.TemporaryDirectory(prefix="mrc-ffmpeg-win64-") as temporary:
            with zipfile.ZipFile(archive) as source:
                source.extractall(temporary)
            ffmpeg_dir.mkdir(parents=True, exist_ok=True)
            for target in ffmpeg_targets:
                matches = list(Path(temporary).rglob(target.name))
                if not matches:
                    raise RuntimeError(f"{target.name} was not found in {archive}")
                shutil.copy2(matches[0], target)
        print(f"Prepared Windows FFmpeg runtime at {ffmpeg_dir}")


if __name__ == "__main__":
    main()
