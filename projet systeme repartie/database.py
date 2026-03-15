import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from queue import Queue


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class DatabasePool:
    def __init__(self, db_path, pool_size=5):
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool = Queue(maxsize=pool_size)

        for _ in range(pool_size):
            connection = sqlite3.connect(db_path, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            self._pool.put(connection)

        self.init_schema()

    def init_schema(self):
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.connection() as connection:
            connection.executescript(schema)
            connection.commit()

    @contextmanager
    def connection(self):
        connection = self._pool.get()
        try:
            yield connection
        finally:
            self._pool.put(connection)

    def close(self):
        while not self._pool.empty():
            connection = self._pool.get_nowait()
            connection.close()


class MonitoringRepository:
    def __init__(self, pool):
        self.pool = pool

    def upsert_node(self, node_id, os_name=None, cpu_model=None, last_ip=None, status="up", last_seen=None, last_alert=None):
        with self.pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO nodes (node_id, os_name, cpu_model, last_ip, status, last_seen, last_alert)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    os_name = COALESCE(excluded.os_name, nodes.os_name),
                    cpu_model = COALESCE(excluded.cpu_model, nodes.cpu_model),
                    last_ip = COALESCE(excluded.last_ip, nodes.last_ip),
                    status = excluded.status,
                    last_seen = COALESCE(excluded.last_seen, nodes.last_seen),
                    last_alert = COALESCE(excluded.last_alert, nodes.last_alert)
                """,
                (node_id, os_name, cpu_model, last_ip, status, last_seen, last_alert),
            )
            connection.commit()

    def save_metrics(self, node_id, timestamp, os_name, cpu_model, cpu_percent, memory_percent, disk_percent, uptime_seconds, alert_any, services, ports, raw_payload):
        with self.pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO metrics (
                    node_id,
                    timestamp,
                    os_name,
                    cpu_model,
                    cpu_percent,
                    memory_percent,
                    disk_percent,
                    uptime_seconds,
                    alert_any,
                    services_json,
                    ports_json,
                    raw_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    timestamp,
                    os_name,
                    cpu_model,
                    cpu_percent,
                    memory_percent,
                    disk_percent,
                    uptime_seconds,
                    int(bool(alert_any)),
                    json.dumps(services, separators=(",", ":")),
                    json.dumps(ports, separators=(",", ":")),
                    json.dumps(raw_payload, separators=(",", ":")),
                ),
            )
            connection.commit()

    def record_event(self, node_id, level, event_type, message, data=None, created_at=None):
        with self.pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO events (created_at, node_id, level, event_type, message, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    node_id,
                    level,
                    event_type,
                    message,
                    json.dumps(data or {}, separators=(",", ":")),
                ),
            )
            connection.commit()

    def list_nodes(self, limit=100):
        with self.pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT node_id, os_name, cpu_model, last_ip, status, last_seen, last_alert
                FROM nodes
                ORDER BY COALESCE(last_seen, '') DESC, node_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_metrics(self, node_id=None, limit=10):
        with self.pool.connection() as connection:
            if node_id:
                rows = connection.execute(
                    """
                    SELECT node_id, timestamp, cpu_percent, memory_percent, disk_percent, uptime_seconds, alert_any
                    FROM metrics
                    WHERE node_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (node_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT node_id, timestamp, cpu_percent, memory_percent, disk_percent, uptime_seconds, alert_any
                    FROM metrics
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def recent_events(self, limit=20, level=None):
        with self.pool.connection() as connection:
            if level:
                rows = connection.execute(
                    """
                    SELECT created_at, node_id, level, event_type, message
                    FROM events
                    WHERE level = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (level, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT created_at, node_id, level, event_type, message
                    FROM events
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]