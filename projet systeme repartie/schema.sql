CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    os_name TEXT,
    cpu_model TEXT,
    last_ip TEXT,
    status TEXT NOT NULL DEFAULT 'unknown',
    last_seen TEXT,
    last_alert TEXT
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREmMENT,
    node_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    os_name TEXT,
    cpu_model TEXT,
    cpu_percent REAL NOT NULL,
    memory_percent REAL NOT NULL,
    disk_percent REAL NOT NULL,
    uptime_seconds REAL NOT NULL,
    alert_any INTEGER NOT NULL DEFAULT 0,
    services_json TEXT NOT NULL,
    ports_json TEXT NOT NULL,
    raw_payload_json TEXT NOT NULL,
    FOREIGN KEY(node_id) REFERENCES nodes(node_id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    node_id TEXT,
    level TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(node_id) REFERENCES nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_metrics_node_timestamp ON metrics(node_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at DESC);