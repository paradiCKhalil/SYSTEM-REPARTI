import argparse
import logging
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from database import DatabasePool, MonitoringRepository
from protocol import ProtocolError, read_messages, send_message, utc_now_iso


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5000
DEFAULT_DB_PATH = "supervision.db"


@dataclass
class NodeSession:
    node_id: str
    sock: socket.socket
    address: str
    send_lock: threading.Lock = field(default_factory=threading.Lock)
    last_seen_monotonic: float = 0.0
    marked_down: bool = False


class MonitoringServer:
    def __init__(self, host, port, db_path, worker_count, db_pool_size, failure_timeout, enable_console=True):
        self.host = host
        self.port = port
        self.failure_timeout = failure_timeout
        self.enable_console = enable_console
        self.stop_event = threading.Event()
        self.server_socket = None
        self.executor = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="client-worker")
        self.db_pool = DatabasePool(db_path, pool_size=db_pool_size)
        self.repository = MonitoringRepository(self.db_pool)
        self.sessions = {}
        self.sessions_lock = threading.Lock()

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        self.server_socket.settimeout(1.0)

        threading.Thread(target=self.monitor_nodes, daemon=True).start()
        if self.enable_console and sys.stdin.isatty():
            threading.Thread(target=self.console_loop, daemon=True).start()
        else:
            logging.info("Console d'administration desactivee: terminal non interactif")

        logging.info("Serveur en ecoute sur %s:%s", self.host, self.port)
        try:
            while not self.stop_event.is_set():
                try:
                    client_socket, client_address = self.server_socket.accept()
                except socket.timeout:
                    continue
                self.executor.submit(self.handle_client, client_socket, client_address)
        finally:
            self.shutdown()

    def shutdown(self):
        if self.stop_event.is_set() and self.server_socket is None:
            return

        self.stop_event.set()

        if self.server_socket is not None:
            try:
                self.server_socket.close()
            except OSError:
                pass
            self.server_socket = None

        with self.sessions_lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()

        for session in sessions:
            try:
                session.sock.close()
            except OSError:
                pass

        self.executor.shutdown(wait=False, cancel_futures=True)
        self.db_pool.close()
        logging.info("Serveur arrete")

    def handle_client(self, client_socket, client_address):
        peer = f"{client_address[0]}:{client_address[1]}"
        node_id = None
        logging.info("Connexion entrante depuis %s", peer)
        try:
            with client_socket:
                with client_socket.makefile("r", encoding="utf-8", newline="\n") as sock_file:
                    for message in read_messages(sock_file):
                        node_id = self.dispatch_message(client_socket, peer, node_id, message)
        except (OSError, ProtocolError) as exc:
            logging.warning("Connexion terminee pour %s: %s", peer, exc)
        finally:
            if node_id:
                self.unregister_session(node_id, reason="socket fermee")

    def dispatch_message(self, client_socket, peer, current_node_id, message):
        message_type = message["type"]
        if message_type == "hello":
            node_id = self.validate_node_id(message)
            self.register_session(node_id, client_socket, peer, message)
            send_message(client_socket, {"type": "ack", "message": "hello recu", "timestamp": utc_now_iso()})
            return node_id

        if message_type == "metrics":
            node_id = self.validate_node_id(message)
            self.process_metrics(node_id, peer, message)
            return node_id

        if message_type == "command_result":
            node_id = self.validate_node_id(message)
            self.process_command_result(node_id, message)
            return node_id

        raise ProtocolError(f"Type de message non supporte: {message_type}")

    @staticmethod
    def validate_node_id(message):
        node_id = message.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise ProtocolError("Le champ node_id est obligatoire")
        return node_id.strip()

    def register_session(self, node_id, client_socket, peer, message):
        os_name = message.get("os_name")
        cpu_model = message.get("cpu_model")
        with self.sessions_lock:
            previous = self.sessions.get(node_id)
            if previous:
                try:
                    previous.sock.close()
                except OSError:
                    pass

            session = NodeSession(node_id=node_id, sock=client_socket, address=peer, last_seen_monotonic=time.monotonic())
            self.sessions[node_id] = session

        self.touch_session(node_id)
        self.repository.upsert_node(
            node_id=node_id,
            os_name=os_name,
            cpu_model=cpu_model,
            last_ip=peer,
            status="up",
            last_seen=utc_now_iso(),
        )
        self.repository.record_event(node_id, "INFO", "NODE_CONNECTED", f"Connexion du noeud {node_id}", {"peer": peer}, utc_now_iso())
        logging.info("Noeud %s enregistre depuis %s", node_id, peer)

    def unregister_session(self, node_id, reason):
        with self.sessions_lock:
            session = self.sessions.pop(node_id, None)

        if session is None:
            return

        timestamp = utc_now_iso()
        self.repository.upsert_node(node_id=node_id, status="disconnected", last_seen=timestamp)
        self.repository.record_event(node_id, "WARNING", "NODE_DISCONNECTED", reason, {}, timestamp)
        logging.warning("Noeud %s deconnecte: %s", node_id, reason)

    def touch_session(self, node_id):
        with self.sessions_lock:
            session = self.sessions.get(node_id)
            if session:
                session.last_seen_monotonic = self.current_time()
                session.marked_down = False

    @staticmethod
    def current_time():
        return time.monotonic()

    def process_metrics(self, node_id, peer, message):
        metrics = message.get("metrics")
        if not isinstance(metrics, dict):
            raise ProtocolError("Le message metrics doit contenir un objet 'metrics'")

        required_fields = [
            "timestamp",
            "os_name",
            "cpu_model",
            "cpu_percent",
            "memory_percent",
            "disk_percent",
            "uptime_seconds",
            "services",
            "ports",
        ]
        for field_name in required_fields:
            if field_name not in metrics:
                raise ProtocolError(f"Champ metrique manquant: {field_name}")

        timestamp = metrics["timestamp"]
        cpu_percent = float(metrics["cpu_percent"])
        memory_percent = float(metrics["memory_percent"])
        disk_percent = float(metrics["disk_percent"])
        uptime_seconds = float(metrics["uptime_seconds"])
        services = metrics["services"]
        ports = metrics["ports"]
        alert_any = bool(metrics.get("alert", cpu_percent > 90 or memory_percent > 90))

        self.repository.upsert_node(
            node_id=node_id,
            os_name=metrics["os_name"],
            cpu_model=metrics["cpu_model"],
            last_ip=peer,
            status="up",
            last_seen=timestamp,
            last_alert=timestamp if alert_any else None,
        )
        self.repository.save_metrics(
            node_id=node_id,
            timestamp=timestamp,
            os_name=metrics["os_name"],
            cpu_model=metrics["cpu_model"],
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            disk_percent=disk_percent,
            uptime_seconds=uptime_seconds,
            alert_any=alert_any,
            services=services,
            ports=ports,
            raw_payload=message,
        )
        self.touch_session(node_id)

        if alert_any:
            alert_message = f"Seuil depasse sur {node_id}: CPU={cpu_percent:.1f}% MEM={memory_percent:.1f}%"
            self.repository.record_event(node_id, "ALERT", "THRESHOLD_EXCEEDED", alert_message, metrics, utc_now_iso())
            logging.warning(alert_message)
        else:
            logging.info("Metriques recues de %s", node_id)

    def process_command_result(self, node_id, message):
        event_level = "INFO" if message.get("success") else "WARNING"
        details = str(message.get("details", "aucun detail"))
        command = str(message.get("command", "UNKNOWN"))
        service = str(message.get("service", "unknown"))
        summary = f"Commande {command} sur {service}: {details}"
        self.repository.record_event(node_id, event_level, "COMMAND_RESULT", summary, message, utc_now_iso())
        logging.info("Resultat commande pour %s: %s", node_id, summary)

    def send_command(self, node_id, command, service):
        with self.sessions_lock:
            session = self.sessions.get(node_id)

        if session is None:
            print(f"Noeud {node_id} non connecte")
            return

        payload = {
            "type": "command",
            "node_id": node_id,
            "timestamp": utc_now_iso(),
            "command": command,
            "service": service,
        }
        try:
            send_message(session.sock, payload, session.send_lock)
        except OSError as exc:
            print(f"Envoi impossible: {exc}")
            self.unregister_session(node_id, reason="commande impossible")
            return

        self.repository.record_event(node_id, "INFO", "COMMAND_SENT", f"Commande {command} envoyee pour {service}", payload, utc_now_iso())
        print(f"Commande {command} envoyee a {node_id} pour le service {service}")

    def monitor_nodes(self):
        while not self.stop_event.wait(5):
            now = self.current_time()
            stale_nodes = []
            with self.sessions_lock:
                for session in self.sessions.values():
                    if session.marked_down:
                        continue
                    if now - session.last_seen_monotonic > self.failure_timeout:
                        session.marked_down = True
                        stale_nodes.append(session.node_id)

            for node_id in stale_nodes:
                timestamp = utc_now_iso()
                message = f"Aucune donnee recue de {node_id} depuis plus de {self.failure_timeout} secondes"
                self.repository.upsert_node(node_id=node_id, status="down", last_alert=timestamp)
                self.repository.record_event(node_id, "ALERT", "NODE_TIMEOUT", message, {}, timestamp)
                logging.error(message)

    def print_nodes(self):
        rows = self.repository.list_nodes()
        if not rows:
            print("Aucun noeud connu")
            return

        for row in rows:
            print(
                f"{row['node_id']:<20} status={row['status']:<12} last_seen={row['last_seen'] or '-':<30} ip={row['last_ip'] or '-'}"
            )

    def print_metrics(self, node_id=None):
        rows = self.repository.latest_metrics(node_id=node_id)
        if not rows:
            print("Aucune metrique disponible")
            return

        for row in rows:
            print(
                f"{row['timestamp']} node={row['node_id']} cpu={row['cpu_percent']:.1f}% mem={row['memory_percent']:.1f}% disk={row['disk_percent']:.1f}% uptime={row['uptime_seconds']:.0f}s alert={bool(row['alert_any'])}"
            )

    def print_events(self, level=None):
        rows = self.repository.recent_events(level=level)
        if not rows:
            print("Aucun evenement")
            return

        for row in rows:
            print(f"{row['created_at']} [{row['level']}] {row['node_id'] or '-'} {row['event_type']} {row['message']}")

    def console_loop(self):
        help_text = (
            "Commandes: help | nodes | metrics [node_id] | alerts | events | up <node_id> <service> | "
            "down <node_id> <service> | quit"
        )
        print(help_text)
        while not self.stop_event.is_set():
            try:
                raw = input("supervision> ").strip()
            except EOFError:
                self.stop_event.set()
                return

            if not raw:
                continue

            parts = raw.split()
            command = parts[0].lower()

            if command == "help":
                print(help_text)
            elif command == "nodes":
                self.print_nodes()
            elif command == "metrics":
                self.print_metrics(parts[1] if len(parts) > 1 else None)
            elif command == "alerts":
                self.print_events(level="ALERT")
            elif command == "events":
                self.print_events()
            elif command in {"up", "down"} and len(parts) == 3:
                self.send_command(parts[1], command.upper(), parts[2].lower())
            elif command == "quit":
                self.stop_event.set()
                return
            else:
                print("Commande invalide. Tapez 'help'.")


def parse_args():
    parser = argparse.ArgumentParser(description="Serveur central de supervision distribuee")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Adresse d'ecoute")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port d'ecoute")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Chemin de la base SQLite")
    parser.add_argument("--workers", type=int, default=12, help="Taille du pool de threads du serveur")
    parser.add_argument("--db-pool-size", type=int, default=4, help="Taille du pool de connexions SQLite")
    parser.add_argument("--failure-timeout", type=int, default=90, help="Delai max sans metrique avant declaration de panne")
    parser.add_argument("--no-console", action="store_true", help="Desactive la console d'administration")
    parser.add_argument("--log-level", default="INFO", help="Niveau de logs")
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    server = MonitoringServer(
        host=args.host
        port=args.port,
        db_path=args.db,
        worker_count=args.workers,
        db_pool_size=args.db_pool_size,
        failure_timeout=args.failure_timeout,
        enable_console=not args.no_console,
    )
    try:
        server.start()
    except KeyboardInterrupt:
        logging.info("Arret demande par l'utilisateur")
        server.shutdown()


if __name__ == "__main__":
    main()