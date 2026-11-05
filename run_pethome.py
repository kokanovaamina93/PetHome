import os
import secrets
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT

if not (BACKEND / "requirements.txt").exists():
    print("Не найден backend/requirements.txt")
    sys.exit(1)

if not (FRONTEND / "package.json").exists():
    print("Не найден package.json в корне проекта")
    sys.exit(1)

if sys.platform == "win32":
    PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
else:
    PYTHON = BACKEND / ".venv" / "bin" / "python"

if not PYTHON.exists():
    print("Не найден Python backend/.venv")
    print("Сначала создай виртуальное окружение:")
    print("  cd backend")
    print("  python3 -m venv .venv")
    print("  source .venv/bin/activate")
    print("  python -m pip install -r requirements.txt")
    sys.exit(1)

env = os.environ.copy()
env.setdefault("PETHOME_SECRET_KEY", secrets.token_urlsafe(48))

print("Проверка зависимостей...")
try:
    subprocess.run(["npm", "--version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except FileNotFoundError:
    print("Node.js / npm не найден в PATH")
    print("Установи Node.js и попробуй ещё раз.")
    sys.exit(1)

backend_proc = None
frontend_proc = None


def stop_all(signum=None, frame=None):
    global backend_proc, frontend_proc
    print("\nОстановка PetHome...")
    for proc in (backend_proc, frontend_proc):
        if proc and proc.poll() is None:
            proc.terminate()
    for proc in (backend_proc, frontend_proc):
        if proc:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    raise KeyboardInterrupt


signal.signal(signal.SIGINT, stop_all)
signal.signal(signal.SIGTERM, stop_all)

try:
    print("Запуск backend...")
    backend_proc = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "main:app", "--reload", "--port", "8000"],
        cwd=str(BACKEND),
        env=env,
        stdout=None,
        stderr=None,
    )

    time.sleep(2)

    print("Запуск frontend...")
    frontend_proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(FRONTEND),
        env=env,
        stdout=None,
        stderr=None,
    )

    print("PetHome запускается...")
    print("Backend: http://127.0.0.1:8000/docs")
    print("Frontend: http://localhost:5173/")
    print("\nНажмите Ctrl+C, чтобы остановить оба сервиса.")

    webbrowser.open("http://localhost:5173/")

    while True:
        if backend_proc.poll() is not None:
            raise RuntimeError("Backend завершился неожиданно")
        if frontend_proc.poll() is not None:
            raise RuntimeError("Frontend завершился неожиданно")
        time.sleep(1)

except KeyboardInterrupt:
    print("\nPetHome остановлен.")
    if backend_proc and backend_proc.poll() is None:
        backend_proc.terminate()
    if frontend_proc and frontend_proc.poll() is None:
        frontend_proc.terminate()
    if backend_proc:
        backend_proc.wait(timeout=10)
    if frontend_proc:
        frontend_proc.wait(timeout=10)
    raise SystemExit(0)
except RuntimeError as exc:
    print(f"Ошибка запуска: {exc}")
    if backend_proc and backend_proc.poll() is None:
        backend_proc.terminate()
    if frontend_proc and frontend_proc.poll() is None:
        frontend_proc.terminate()
    raise SystemExit(1)
