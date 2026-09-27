"""Build a distributable of Universal Convert.

Run from the repository root:

    python installers/build_release.py --version 0.1.0

What comes out of dist/:

    Windows:  Universal-Convert-<v>-windows.exe       (double-click / menu verb)
              Universal-Convert-<v>-windows-cli.exe   (keeps --cli output)
    macOS:    Universal-Convert-<v>-macos.dmg
    Linux:    Universal-Convert-<v>-linux-x86_64.AppImage  (tar.gz fallback)

Every build is smoke tested (converts a generated PNG through the built
binary) before it is packaged, so a broken bundle never reaches a release.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
ICONS = ROOT / "installers" / "icons"

APPHASH = "universal-convert"
PRETTY = "Universal Convert"

APPIMAGETOOL_URLS = (
    "https://github.com/AppImage/appimagetool/releases/download/continuous/"
    "appimagetool-x86_64.AppImage",
    "https://github.com/AppImage/AppImageKit/releases/download/13/"
    "appimagetool-x86_64.AppImage",
)


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kw)


def ensure_icons() -> None:
    if (ICONS / "icon.png").exists() and (ICONS / "icon.ico").exists():
        return
    sh([sys.executable, str(ROOT / "installers" / "make_icon.py")])


def pyinstaller(args: list[str]) -> None:
    sh([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", *args])


def common_flags(name: str) -> list[str]:
    flags = [
        "--name", name,
        "--paths", str(ROOT),
        "--windowed",
        "--add-data", f"{ROOT / 'config' / 'settings.json'}{os.pathsep}config",
    ]
    if sys.platform == "darwin":
        flags += ["--icon", str(ICONS / "icon.icns")]
    else:
        # Windows/Linux ship as a single file; on macOS PyInstaller makes a
        # .app bundle out of the onedir build (that is what the dmg needs)
        flags += ["--onefile"]
        if sys.platform == "win32":
            flags += ["--icon", str(ICONS / "icon.ico")]
    flags.append(str(ROOT / "main.py"))
    return flags


def run_smoke(binary: Path, expect_stdout: bool = True) -> None:
    """Convert a generated PNG through `binary`; fail loudly on any error.

    expect_stdout=False is for the windowed Windows build, which has no
    stdout at all (PyInstaller nulls it) - only exit codes can be checked.
    """
    from PIL import Image

    with tempfile.TemporaryDirectory(prefix="uc-smoke-") as tmp:
        tmp_path = Path(tmp)
        sample = tmp_path / "smoke.png"
        Image.new("RGB", (120, 80), (30, 144, 255)).save(sample)

        info = subprocess.run(
            [str(binary), "--info", str(sample)],
            capture_output=True, text=True, timeout=300,
        )
        if info.returncode != 0:
            raise SystemExit(
                f"smoke: {binary.name} --info failed "
                f"(rc={info.returncode})\n{info.stdout}\n{info.stderr}"
            )
        if expect_stdout and "convert" not in info.stdout:
            raise SystemExit(f"smoke: {binary.name} --info printed:\n{info.stdout}")

        before = set(tmp_path.iterdir())
        conv = subprocess.run(
            [str(binary), "--cli", "--action", "resize", "--width", "40",
             "--out", "same", str(sample)],
            capture_output=True, text=True, timeout=300,
        )
        after = set(tmp_path.iterdir())
        created = after - before
        if conv.returncode != 0 or not created:
            raise SystemExit(
                f"smoke: {binary.name} conversion failed "
                f"(rc={conv.returncode}, created={sorted(p.name for p in created)})\n"
                f"{conv.stdout}\n{conv.stderr}"
            )
        made = next(iter(created))
        with Image.open(made) as check:
            if check.size[0] > 40:
                raise SystemExit(f"smoke: {made.name} came out {check.size}")
    print(f"smoke test passed: {binary}")


def artifact_name(version: str, suffix: str) -> Path:
    return DIST / f"Universal-Convert-{version}-{suffix}"


def build_windows(version: str) -> list[Path]:
    pyinstaller(common_flags("UniversalConvert"))
    exe = DIST / "UniversalConvert.exe"
    if not exe.exists():
        raise SystemExit("windows: build produced no UniversalConvert.exe")

    # a second, console build so `UniversalConvert-cli.exe --cli ...` still
    # prints its report (the windowed one has no stdout at all)
    cli_ok = True
    try:
        pyinstaller([
            "--name", "UniversalConvertCLI",
            "--paths", str(ROOT),
            "--onefile",
            "--icon", str(ICONS / "icon.ico"),
            "--add-data",
            f"{ROOT / 'config' / 'settings.json'}{os.pathsep}config",
            str(ROOT / "main.py"),
        ])
    except subprocess.CalledProcessError:
        cli_ok = False
    cli_exe = DIST / "UniversalConvertCLI.exe"
    if not cli_exe.exists():
        cli_ok = False

    run_smoke(exe, expect_stdout=False)
    if cli_ok:
        run_smoke(cli_exe)

    out = artifact_name(version, "windows.exe")
    shutil.copy2(exe, out)
    made = [out]
    if cli_ok:
        cli_out = artifact_name(version, "windows-cli.exe")
        shutil.copy2(cli_exe, cli_out)
        made.append(cli_out)
    return made


def build_macos(version: str) -> list[Path]:
    pyinstaller(common_flags("UniversalConvert"))
    app = DIST / "UniversalConvert.app"
    if not app.exists():
        raise SystemExit("macos: build produced no UniversalConvert.app")

    run_smoke(app / "Contents" / "MacOS" / "UniversalConvert",
              expect_stdout=False)

    staging = BUILD / "dmg-staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    shutil.copytree(app, staging / app.name, symlinks=True)
    os.symlink("/Applications", str(staging / "Applications"))

    out = artifact_name(version, "macos.dmg")
    sh([
        "hdiutil", "create", "-volname", PRETTY, "-srcfolder", str(staging),
        "-ov", "-format", "UDZO", str(out),
    ])
    return [out]


def _download(url: str, dest: Path) -> None:
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def build_linux(version: str) -> list[Path]:
    pyinstaller(common_flags(APPHASH))
    binary = DIST / APPHASH
    if not binary.exists():
        raise SystemExit("linux: build produced no binary")
    run_smoke(binary)

    appdir = BUILD / "AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    appdir.mkdir(parents=True)

    shutil.copy2(binary, appdir / APPHASH)
    os.chmod(appdir / APPHASH, 0o755)
    os.symlink(APPHASH, str(appdir / "AppRun"))
    shutil.copy2(ICONS / "icon.png", appdir / f"{APPHASH}.png")
    os.symlink(f"{APPHASH}.png", str(appdir / ".DirIcon"))

    (appdir / f"{APPHASH}.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={PRETTY}\n"
        "Comment=Convert images, PDFs and Office documents\n"
        f"Exec={APPHASH} %F\n"
        f"Icon={APPHASH}\n"
        "Categories=Utility;Graphics;Office;\n"
        "Terminal=false\n",
        encoding="utf-8",
    )

    out = artifact_name(version, "linux-x86_64.AppImage")
    tool = BUILD / "appimagetool.AppImage"
    env = dict(os.environ, ARCH="x86_64")
    for url in APPIMAGETOOL_URLS:
        try:
            _download(url, tool)
            os.chmod(tool, 0o755)
            sh([
                str(tool), "--appimage-extract-and-run",
                str(appdir), str(out),
            ], env=env)
            return [out]
        except Exception as exc:  # noqa: BLE001 - fall through to tarball
            print(f"appimagetool failed ({exc}); trying next source / tarball")

    fallback = artifact_name(version, "linux-x86_64.tar.gz")
    with tarfile.open(fallback, "w:gz") as tar:
        tar.add(appdir, arcname=PRETTY.replace(" ", "-"))
    return [fallback]


def write_checksums(paths: list[Path]) -> Path:
    lines = []
    for path in sorted(paths):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    out = DIST / "SHA256SUMS.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="dev")
    args = parser.parse_args()

    ensure_icons()
    DIST.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)

    if sys.platform == "win32":
        made = build_windows(args.version)
    elif sys.platform == "darwin":
        made = build_macos(args.version)
    else:
        made = build_linux(args.version)

    write_checksums(made)
    print("built:")
    for path in made:
        print(f"  {path.name}  {path.stat().st_size // 1024} KiB")
    print(f"host: {platform.platform()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
