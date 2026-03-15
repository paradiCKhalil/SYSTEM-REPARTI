import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_COUNT = 10
DEFAULT_DURATION = 30
DEFAULT_HOST = "127.0.0.1"
DEFAULT_INTERVAL = 5
DEFAULT_LOG_DIR = "load-test-logs2"
DEFAULT_NODE_PREFIX = "demo-node-jj"
DEFAULT_PORT = 5000
DEFAULT_STAGGER = 0.05


def parse_args():
    parser = argparse.ArgumentParser(description="Lance plusieurs agents pour une demonstration de charge")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="Nombre de clients a lancer")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION, help="Duree totale du test en secondes")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Adresse du serveur central")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port du serveur central")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Intervalle d'envoi des metriques")
    parser.add_argument("--node-prefix", default=DEFAULT_NODE_PREFIX, help="Prefixe des identifiants de noeuds")
    parser.add_argument("--stagger", type=float, default=DEFAULT_STAGGER, help="Delai entre deux lancements de clients")
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR, help="Dossier de sortie des logs clients")
    parser.add_argument("--python", default=sys.executable, help="Executable Python a utiliser")
    parser.add_argument("--client-script", default="client.py", help="Chemin du script client")
    return parser.parse_args()


def validate_args(args):
    if args.count <= 0:
        raise ValueError("--count doit etre strictement positif")
    if args.duration <= 0:
        raise ValueError("--duration doit etre strictement positif")
    if args.interval <= 0:
        raise ValueError("--interval doit etre strictement positif")
    if args.stagger < 0:
        raise ValueError("--stagger ne peut pas etre negatif")


def build_client_command(args, node_id):
    return [
        args.python,
        args.client_script,
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--interval",
        str(args.interval),
        "--node-id",
        node_id,
        "--log-level",
        "WARNING",
    ]


def terminate_process(process):
    if process.poll() is not None:
        return

    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        process.terminate()

    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    args = parse_args()
    validate_args(args)

    workspace_dir = Path(__file__).resolve().parent
    log_dir = (workspace_dir / args.log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    started_processes = []
    deadline = time.monotonic() + args.duration

    print(
        f"Demarrage de {args.count} clients vers {args.host}:{args.port} pendant {args.duration}s. Logs: {log_dir}"
    )

    try:
        for index in range(1, args.count + 1):
            node_id = f"{args.node_prefix}-{index:03d}"
            command = build_client_command(args, node_id)
            log_path = log_dir / f"{node_id}.log"
            log_handle = log_path.open("w", encoding="utf-8")
            process = subprocess.Popen(command, cwd=workspace_dir, stdout=log_handle, stderr=subprocess.STDOUT)
            started_processes.append((node_id, process, log_handle))
            print(f"Lance {node_id} pid={process.pid}")
            if args.stagger:
                time.sleep(args.stagger)

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(1.0, remaining))

    except KeyboardInterrupt:
        print("Interruption utilisateur, arret des clients...")
    finally:
        for node_id, process, log_handle in reversed(started_processes):
            try:
                terminate_process(process)
            finally:
                log_handle.close()
            exit_code = process.returncode
            print(f"Arret {node_id} code={exit_code}")


if __name__ == "__main__":
    main()