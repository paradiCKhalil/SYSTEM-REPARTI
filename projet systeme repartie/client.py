import argparse
import logging
import platform
import socket
import threading
import time

import psutil

from protocol import ProtocolError, read_messages, send_message, utc_now_iso


DEFAULT_INTERVAL = 10
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 5000
RECONNECT_DELAY = 5
PREDEFINED_PORTS = [22, 80, 443, 3306]
DEFAULT_SERVICES = {
    "ssh": ["sshd", "ssh"],
    "nginx": ["nginx"],
    "docker": ["dockerd", "docker"],
    "firefox": ["firefox"],
    "chrome": ["chrome", "chromium", "google-chrome"],
    "code": ["code", "code-insiders"],
}


class SupervisionClient:
    def __init__(self, server_host, server_port, interval, node_id):
        self.server_host = server_host
        self.server_port = server_port
        self.interval = interval
        self.node_id = node_id or platform.node() or socket.gethostname()
        self.stop_event = threading.Event()
        self.send_lock = threading.Lock()
        self.service_overrides = {}
        self.services_lock = threading.Lock()
        psutil.cpu_percent(interval=None)

    def collect_metrics(self):
        cpu_percent = psutil.cpu_percent(interval=0.2)
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage("/").percent
        uptime_seconds = time.time() - psutil.boot_time()
        services = self.collect_services()
        ports = self.collect_ports()
        alert_any = cpu_percent > 90 or memory_percent > 90

        return {
            "node_id": self.node_id,
            "timestamp": utc_now_iso(),
            "os_name": platform.system(),
            "cpu_model": platform.processor() or platform.machine(),
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "disk_percent": disk_percent,
            "uptime_seconds": uptime_seconds,
            "alert": alert_any,
            "services": services,
            "ports": ports,
        }

    def collect_services(self):
        observed = {}
        for service_name, candidates in DEFAULT_SERVICES.items():
            observed[service_name] = self.process_exists(candidates)

        with self.services_lock:
            observed.update(self.service_overrides)

        return observed

    def collect_ports(self):
        port_states = {}
        for port in PREDEFINED_PORTS:
            port_states[str(port)] = self.is_port_open(port)
        return port_states

    @staticmethod
    def process_exists(candidates):
        lowered = {candidate.lower() for candidate in candidates}
        for process in psutil.process_iter(attrs=["name"]):
            name = (process.info.get("name") or "").lower()
            if name in lowered:
                return True
        return False

    @staticmethod
    def is_port_open(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.3)
            try:
                return probe.connect_ex(("127.0.0.1", port)) == 0
            except OSError:
                return False

    def hello_message(self):
        return {
            "type": "hello",
            "node_id": self.node_id,
            "timestamp": utc_now_iso(),
            "os_name": platform.system(),
            "cpu_model": platform.processor() or platform.machine(),
        }

    def metrics_message(self):
        return {
            "type": "metrics",
            "node_id": self.node_id,
            "timestamp": utc_now_iso(),
            "metrics": self.collect_metrics(),
        }

    def command_result_message(self, command, service, success, details):
        return {
            "type": "command_result",
            "node_id": self.node_id,
            "timestamp": utc_now_iso(),
            "command": command,
            "service": service,
            "success": bool(success),
            "details": details,
        }

    def handle_message(self, sock, message):
        message_type = message.get("type")
        if message_type in {"ack", "error"}:
            logging.info("Reponse serveur: %s", message)
            return

        if message_type != "command":
            logging.warning("Message ignore: %s", message)
            return

        command = str(message.get("command", "")).upper()
        service = str(message.get("service", "")).lower()
        if service not in DEFAULT_SERVICES:
            response = self.command_result_message(command, service, False, "service inconnue")
            send_message(sock, response, self.send_lock)
            return

        if command not in {"UP", "DOWN"}:
            response = self.command_result_message(command, service, False, "commande inconnue")
            send_message(sock, response, self.send_lock)
            return

        with self.services_lock:
            self.service_overrides[service] = command == "UP"

        details = f"service {service} forcee a {command}"
        logging.info(details)
        send_message(sock, self.command_result_message(command, service, True, details), self.send_lock)

    def receive_loop(self, sock_file, sock):
        try:
            for message in read_messages(sock_file):
                self.handle_message(sock, message)
        except (OSError, ProtocolError) as exc:
            if not self.stop_event.is_set():
                logging.warning("Reception interrompue: %s", exc)

    def run(self):
        while not self.stop_event.is_set():
            try:
                with socket.create_connection((self.server_host, self.server_port), timeout=10) as sock:
                    sock.settimeout(None)
                    with sock.makefile("r", encoding="utf-8", newline="\n") as sock_file:
                        receiver = threading.Thread(target=self.receive_loop, args=(sock_file, sock), daemon=True)
                        receiver.start()
                        send_message(sock, self.hello_message(), self.send_lock)
                        logging.info("Connecte au serveur %s:%s", self.server_host, self.server_port)

                        while not self.stop_event.is_set():
                            send_message(sock, self.metrics_message(), self.send_lock)
                            self.stop_event.wait(self.interval)
            except OSError as exc:
                logging.warning("Connexion impossible ou interrompue: %s", exc)

            if not self.stop_event.is_set():
                time.sleep(RECONNECT_DELAY)


def parse_args():
    parser = argparse.ArgumentParser(description="Agent de supervision distribue")
    parser.add_argument("--host", default=DEFAULT_SERVER_HOST, help="Adresse du serveur central")
    parser.add_argument("--port", type=int, default=DEFAULT_SERVER_PORT, help="Port du serveur central")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Frequence d'envoi des metriques en secondes")
    parser.add_argument("--node-id", default=None, help="Identifiant logique du noeud")
    parser.add_argument("--log-level", default="INFO", help="Niveau de logs")
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    client = SupervisionClient(args.host, args.port, args.interval, args.node_id)
    client.run()


if __name__ == "__main__":
    main()