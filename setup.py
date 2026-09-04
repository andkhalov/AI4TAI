#!/usr/bin/env python3
"""AI4TAI setup — установка на Windows, macOS и Linux.

  1. Проверка Python 3.10+ и системных зависимостей (git, curl; на Linux tar/bzip2/libgomp1)
  2. Создание .venv и pip install -r requirements.txt
  3. Скачивание Goose CLI в .tools/
  4. Запуск cli/wizard.py (если .env не существует)
  5. Сборка учебной базы data/demo.sqlite
  6. Symlink ~/.local/bin/ai4tai (Linux/macOS)
  7. Проверка: bin/ai4tai doctor

Использование:
    python setup.py
    python setup.py --skip-goose      # без скачивания Goose (только venv, база, проверки)
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

REPO = Path(__file__).resolve().parent
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
# Версия Goose закреплена: проверена с этим репозиторием (Windows/macOS/Linux).
GOOSE_RELEASE = os.environ.get("AI4TAI_GOOSE_RELEASE", "https://github.com/aaif-goose/goose/releases/download/v1.49.0")

if sys.stdout.isatty() and not os.environ.get("AI4TAI_NOCOLOR"):
    GREEN, YELLOW, RED, RESET = "\033[0;32m", "\033[0;33m", "\033[0;31m", "\033[0m"
else:
    GREEN = YELLOW = RED = RESET = ""


def say(msg: str) -> None:
    print(f"{GREEN}[AI4TAI]{RESET} {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"{YELLOW}[AI4TAI]{RESET} {msg}", flush=True)


def die(msg: str, code: int = 1) -> "NoReturn":  # noqa: F821
    print(f"{RED}[AI4TAI]{RESET} {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


# ---------- pre-flight ----------

def check_python_version() -> None:
    if sys.version_info < (3, 10):
        die(f"Нужен Python 3.10+ (сейчас: {platform.python_version()})")
    say(f"Python: {platform.python_version()} ({sys.executable})")


def check_system_deps() -> None:
    missing = [c for c in ("git", "curl") if shutil.which(c) is None]
    if IS_LINUX:
        missing += [c for c in ("tar", "bzip2") if shutil.which(c) is None]
        found = any(Path(d, "libgomp.so.1").exists() for d in (
            "/usr/lib/x86_64-linux-gnu", "/usr/lib/aarch64-linux-gnu", "/usr/lib64", "/usr/lib",
            "/lib/x86_64-linux-gnu", "/lib/aarch64-linux-gnu", "/lib64", "/lib"))
        if not found:
            missing.append("libgomp1")
    if missing:
        warn(f"Не хватает: {' '.join(missing)}")
        if IS_WINDOWS:
            print("    Windows: git — https://git-scm.com/download/win; curl входит в Windows 10+")
        elif IS_MACOS:
            print(f"    macOS: brew install {' '.join(missing)}")
        else:
            print(f"    Debian/Ubuntu: sudo apt-get install -y {' '.join(missing)}")
        die("Установи зависимости и запусти setup заново.")


# ---------- venv ----------

def venv_python() -> Path:
    return REPO / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python")


def setup_venv() -> Path:
    venv = REPO / ".venv"
    if not venv.exists():
        say("Создаю .venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    py = venv_python()
    if not py.exists():
        die(f".venv сломан — нет {py}")
    say("Устанавливаю зависимости из requirements.txt ...")
    subprocess.check_call([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    subprocess.check_call([str(py), "-m", "pip", "install", "--quiet", "-r", str(REPO / "requirements.txt")])
    say("Зависимости установлены.")
    return py


# ---------- goose ----------

def _goose_asset_name() -> str:
    arch_raw = platform.machine().lower()
    if arch_raw in ("x86_64", "amd64"):
        arch = "x86_64"
    elif arch_raw in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        die(f"Неподдерживаемая архитектура: {arch_raw}")
    if IS_LINUX:
        return f"goose-{arch}-unknown-linux-gnu.tar.bz2"
    if IS_MACOS:
        return f"goose-{arch}-apple-darwin.tar.bz2"
    if IS_WINDOWS:
        if arch != "x86_64":
            die("Windows: Goose доступен только для x86_64")
        return "goose-x86_64-pc-windows-msvc.zip"
    die(f"Неподдерживаемая ОС: {sys.platform}")


def install_goose() -> Path:
    tools_dir = REPO / ".tools"
    goose_exe = tools_dir / ("goose.exe" if IS_WINDOWS else "goose")
    if goose_exe.exists():
        try:
            out = subprocess.check_output([str(goose_exe), "--version"], text=True, stderr=subprocess.STDOUT, timeout=20)
            say(f"Goose уже установлен: {out.strip().splitlines()[-1]}")
            return goose_exe
        except Exception:
            warn("Goose есть, но не запускается. Переустановка ...")
            goose_exe.unlink()
    tools_dir.mkdir(parents=True, exist_ok=True)
    asset = _goose_asset_name()
    url = f"{GOOSE_RELEASE}/{asset}"
    say(f"Скачиваю Goose: {url}")
    with tempfile.TemporaryDirectory(prefix="ai4tai-goose-") as td:
        td_path = Path(td)
        archive = td_path / asset
        try:
            urllib.request.urlretrieve(url, archive)
        except Exception as e:
            die(f"Не удалось скачать Goose: {e}")
        say(f"  скачано: {archive.stat().st_size:,} байт")
        if asset.endswith(".tar.bz2"):
            import tarfile
            with tarfile.open(archive, "r:bz2") as tf:
                tf.extractall(td_path)
            src = next((p for p in td_path.rglob("goose") if p.is_file()), None)
            if src is None:
                die("goose не найден в архиве")
            shutil.move(str(src), str(goose_exe))
            goose_exe.chmod(0o755)
        else:
            import zipfile
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(td_path)
            src = next((p for p in td_path.rglob("*") if p.is_file() and p.name.lower() == "goose.exe"), None)
            if src is None:
                die("goose.exe не найден в архиве")
            shutil.move(str(src), str(goose_exe))
            for dll in src.parent.glob("*.dll"):
                dest = tools_dir / dll.name
                if not dest.exists():
                    shutil.move(str(dll), str(dest))
    try:
        out = subprocess.check_output([str(goose_exe), "--version"], text=True, stderr=subprocess.STDOUT, timeout=20)
        say(f"Goose: {out.strip().splitlines()[-1]}")
    except Exception as e:
        die(f"Goose установлен, но не запускается: {type(e).__name__}: {e}")
    return goose_exe


# ---------- wizard, data, symlink, doctor ----------

def run_wizard(py: Path) -> None:
    env_file = REPO / ".env"
    if env_file.exists():
        warn(".env уже существует — wizard пропущен. Удали .env и перезапусти setup для перенастройки.")
        return
    say("Запускаю cli/wizard.py ...")
    subprocess.check_call([str(py), str(REPO / "cli" / "wizard.py")])


def build_demo_db(py: Path) -> None:
    say("Собираю учебную базу data/demo.sqlite ...")
    subprocess.check_call([str(py), str(REPO / "src" / "demo_db.py")])


def create_symlink() -> None:
    if IS_WINDOWS:
        warn(f"Windows: запуск через bin\\ai4tai.bat; для команды ai4tai добавь {REPO}\\bin в PATH.")
        return
    target = Path.home() / ".local" / "bin" / "ai4tai"
    if target.exists() or target.is_symlink():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(REPO / "bin" / "ai4tai")
        say(f"Symlink: {target}")
        if str(target.parent) not in os.environ.get("PATH", "").split(os.pathsep):
            warn(f"{target.parent} нет в PATH. Добавь: export PATH=\"{target.parent}:$PATH\"")
    except OSError as e:
        warn(f"Symlink не создан: {e}")


def run_doctor(py: Path) -> None:
    say("Проверка: bin/ai4tai doctor ...")
    rc = subprocess.call([str(py), str(REPO / "bin" / "ai4tai.py"), "doctor"])
    if rc != 0:
        die("doctor завершился с ошибкой — установка не завершена.", rc)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI4TAI setup")
    ap.add_argument("--skip-goose", action="store_true", help="не скачивать Goose")
    ap.add_argument("--skip-doctor", action="store_true", help="не запускать doctor в конце")
    args = ap.parse_args()

    say(f"=== AI4TAI setup ({sys.platform}, Python {platform.python_version()}, {platform.machine()}) ===")
    say(f"repo: {REPO}")
    say("[1/7] системные зависимости")
    check_system_deps()
    say("[2/7] версия Python")
    check_python_version()
    say("[3/7] venv и зависимости")
    py = setup_venv()
    say("[4/7] Goose CLI")
    if args.skip_goose:
        warn("пропущено (--skip-goose)")
    else:
        install_goose()
    say("[5/7] .env (wizard)")
    run_wizard(py)
    say("[6/7] учебная база")
    build_demo_db(py)
    say("[7/7] symlink и проверка")
    create_symlink()
    if not args.skip_doctor:
        run_doctor(py)

    print()
    say("Готово. Запуск:")
    if IS_WINDOWS:
        print("    bin\\ai4tai.bat                 интерактивная сессия")
        print('    bin\\ai4tai.bat run "промпт"    одна задача')
        print("    bin\\ai4tai.bat doctor          проверка окружения")
    else:
        print("    ai4tai                         интерактивная сессия")
        print('    ai4tai run "промпт"            одна задача')
        print("    ai4tai doctor                  проверка окружения")
    print("\nДокументация: README.md, docs/ARCHITECTURE.md")
    return 0


if __name__ == "__main__":
    import traceback
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
    except subprocess.CalledProcessError as e:
        print(f"{RED}[AI4TAI]{RESET} команда завершилась с ошибкой: {e.cmd} (rc={e.returncode})", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"{RED}[AI4TAI]{RESET} ошибка: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(2)
