"""Запустить оба сервиса; Ctrl+C останавливает только их процессы."""
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def main():
    for port in [8010, 8011]:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                print(f"Порт {port} занят. Закрой предыдущий запуск сервисов.")
                return 1
    processes = []
    files = []
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        for target, port, filename in [
            ("notify_service:app_notify", 8011, "notify_service.log"),
            ("main:app", 8010, "user_service.log"),
        ]:
            log = (ROOT / filename).open("w", buffering=1)
            files.append(log)
            processes.append(subprocess.Popen(
                [sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            ))
        print("User Service: http://127.0.0.1:8010/docs", flush=True)
        print("Уведомления: http://127.0.0.1:8011/notifications/", flush=True)
        print("Оставь это окно открытым. Ctrl+C — остановить оба сервиса.", flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
        print("Один из сервисов завершился. Проверь файлы *.log.")
        return 1
    except KeyboardInterrupt:
        print("Останавливаю сервисы…", flush=True)
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in files:
            log.close()


if __name__ == "__main__":
    sys.exit(main())
