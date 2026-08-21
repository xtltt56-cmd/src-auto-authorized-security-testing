import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import InsertResult


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                target_id TEXT NOT NULL,
                scope_hash TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assets (
                fingerprint TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER,
                url TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'web',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS asset_snapshots (
                run_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                PRIMARY KEY(run_id, fingerprint)
            );
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                parameter TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL DEFAULT 'info',
                evidence TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'candidate',
                triage_json TEXT NOT NULL DEFAULT '{}',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS finding_runs (
                run_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                PRIMARY KEY(run_id, fingerprint)
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_fingerprint TEXT NOT NULL,
                path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(run_id, stage)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS spend (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                run_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                run_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                bounty REAL,
                manual_time_minutes REAL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                finding_fingerprint TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                disposition TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                suggested_checks_json TEXT NOT NULL DEFAULT '[]',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_usd REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        spend_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(spend)")}
        if "run_id" not in spend_columns:
            self.conn.execute("ALTER TABLE spend ADD COLUMN run_id TEXT")
        self.conn.execute(
            "INSERT OR IGNORE INTO finding_runs(run_id,fingerprint,first_seen,last_seen) "
            "SELECT run_id,fingerprint,first_seen,last_seen FROM findings WHERE run_id <> ''"
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def create_run(self, target_id: str, scope_hash: str, mode: str = "local") -> str:
        run_id = uuid.uuid4().hex
        now = utc_now()
        self.conn.execute(
            "INSERT INTO runs(run_id,target_id,scope_hash,mode,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (run_id, target_id, scope_hash, mode, "created", now, now),
        )
        self.conn.commit()
        return run_id

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM runs ORDER BY created_at DESC")]

    def set_run_status(self, run_id: str, status: str) -> None:
        self.conn.execute("UPDATE runs SET status=?,updated_at=? WHERE run_id=?", (status, utc_now(), run_id))
        self.conn.commit()

    def save_checkpoint(self, run_id: str, stage: str, payload: Dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO checkpoints(run_id,stage,payload_json,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(run_id,stage) DO UPDATE SET payload_json=excluded.payload_json,updated_at=excluded.updated_at",
            (run_id, stage, json.dumps(payload, ensure_ascii=False, sort_keys=True), utc_now()),
        )
        self.conn.commit()

    def load_checkpoint(self, run_id: str, stage: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT payload_json FROM checkpoints WHERE run_id=? AND stage=?", (run_id, stage)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def record_event(self, run_id: str, level: str, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self.conn.execute(
            "INSERT INTO events(run_id,level,message,payload_json,created_at) VALUES(?,?,?,?,?)",
            (run_id, level, message, json.dumps(payload or {}, ensure_ascii=False, sort_keys=True), utc_now()),
        )
        self.conn.commit()

    def record_spend(self, amount: float, category: str, run_id: Optional[str] = None) -> None:
        if float(amount) < 0:
            raise ValueError("spend amount cannot be negative")
        self.conn.execute(
            "INSERT INTO spend(amount,category,run_id,created_at) VALUES(?,?,?,?)",
            (float(amount), str(category), run_id, utc_now()),
        )
        self.conn.commit()

    def spend_summary(self) -> Dict[str, Any]:
        total = float(self.conn.execute("SELECT COALESCE(SUM(amount),0) FROM spend").fetchone()[0])
        by_category = {
            str(row[0]): float(row[1])
            for row in self.conn.execute("SELECT category,SUM(amount) FROM spend GROUP BY category")
        }
        return {"total": total, "by_category": by_category}

    def insert_ai_review(self, review: Dict[str, Any]) -> int:
        """Persist one manually confirmed remote review without changing Finding state."""
        try:
            confidence = max(0.0, min(1.0, float(review.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            input_tokens = max(0, int(review.get("input_tokens", 0)))
        except (TypeError, ValueError):
            input_tokens = 0
        try:
            output_tokens = max(0, int(review.get("output_tokens", 0)))
        except (TypeError, ValueError):
            output_tokens = 0
        try:
            estimated_cost_usd = max(0.0, float(review.get("estimated_cost_usd", 0.0)))
        except (TypeError, ValueError):
            estimated_cost_usd = 0.0
        checks = review.get("suggested_checks", [])
        if not isinstance(checks, list):
            checks = []
        cursor = self.conn.execute(
            "INSERT INTO ai_reviews(run_id,finding_fingerprint,provider,model,payload_digest,"
            "disposition,confidence,reason,suggested_checks_json,input_tokens,output_tokens,"
            "estimated_cost_usd,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(review.get("run_id", "")),
                str(review.get("finding_fingerprint", "")),
                str(review.get("provider", "")),
                str(review.get("model", "")),
                str(review.get("payload_digest", "")),
                str(review.get("disposition", "manual_review")),
                confidence,
                str(review.get("reason", "")),
                json.dumps(checks, ensure_ascii=False, sort_keys=True),
                input_tokens,
                output_tokens,
                estimated_cost_usd,
                utc_now(),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def list_ai_reviews(
        self, run_id: Optional[str] = None, finding_fingerprint: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        clauses = []
        values = []
        if run_id:
            clauses.append("run_id=?")
            values.append(str(run_id))
        if finding_fingerprint:
            clauses.append("finding_fingerprint=?")
            values.append(str(finding_fingerprint))
        query = "SELECT * FROM ai_reviews"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC"
        rows = self.conn.execute(query, values).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["suggested_checks"] = json.loads(item.pop("suggested_checks_json"))
            result.append(item)
        return result

    def ai_review_summary(self) -> Dict[str, Any]:
        count, estimated_cost = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(estimated_cost_usd),0) FROM ai_reviews"
        ).fetchone()
        by_provider = {
            str(row[0]): {"count": int(row[1]), "estimated_cost_usd": float(row[2] or 0)}
            for row in self.conn.execute(
                "SELECT provider,COUNT(*),COALESCE(SUM(estimated_cost_usd),0) "
                "FROM ai_reviews GROUP BY provider ORDER BY provider"
            )
        }
        return {
            "count": int(count),
            "estimated_cost_usd": float(estimated_cost),
            "by_provider": by_provider,
        }

    def record_submission(
        self,
        finding_fingerprint: str,
        status: str,
        bounty: Optional[float] = None,
        manual_time_minutes: Optional[float] = None,
    ) -> int:
        cursor = self.conn.execute(
            "INSERT INTO submissions(finding_fingerprint,status,bounty,manual_time_minutes,created_at) VALUES(?,?,?,?,?)",
            (str(finding_fingerprint), str(status), bounty, manual_time_minutes, utc_now()),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def list_submissions(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM submissions ORDER BY id DESC")]

    def list_events(self, run_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def upsert_asset(self, run_id: str, asset: Dict[str, Any]) -> str:
        host = str(asset.get("host", "")).lower().rstrip(".")
        port = int(asset["port"]) if asset.get("port") is not None else None
        url = str(asset.get("url", ""))
        kind = str(asset.get("kind", "web"))
        metadata = dict(asset.get("metadata", {}))
        fingerprint = stable_hash({"host": host, "port": port, "url": url, "kind": kind})
        now = utc_now()
        self.conn.execute(
            "INSERT INTO assets(fingerprint,run_id,host,port,url,kind,metadata_json,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(fingerprint) DO UPDATE SET run_id=excluded.run_id,metadata_json=excluded.metadata_json,last_seen=excluded.last_seen",
            (fingerprint, run_id, host, port, url, kind, json.dumps(metadata, ensure_ascii=False, sort_keys=True), now, now),
        )
        self.conn.commit()
        return fingerprint

    def snapshot_assets(self, run_id: str, assets: Iterable[Dict[str, Any]]) -> List[str]:
        fingerprints = []
        for asset in assets:
            fingerprint = self.upsert_asset(run_id, asset)
            fingerprints.append(fingerprint)
            self.conn.execute(
                "INSERT OR IGNORE INTO asset_snapshots(run_id,fingerprint) VALUES(?,?)", (run_id, fingerprint)
            )
        self.conn.commit()
        return fingerprints

    def diff_assets(self, previous_run_id: str, current_run_id: str) -> Dict[str, List[str]]:
        old = {row[0] for row in self.conn.execute("SELECT fingerprint FROM asset_snapshots WHERE run_id=?", (previous_run_id,))}
        new = {row[0] for row in self.conn.execute("SELECT fingerprint FROM asset_snapshots WHERE run_id=?", (current_run_id,))}
        return {"added": sorted(new - old), "removed": sorted(old - new), "unchanged": sorted(old & new)}

    def insert_finding(self, finding: Dict[str, Any]) -> InsertResult:
        title = str(finding.get("title", "")).strip()
        url = str(finding.get("url", "")).strip()
        parameter = str(finding.get("parameter", "")).strip()
        fingerprint = stable_hash({"title": title.lower(), "url": url.lower(), "parameter": parameter.lower()})
        now = utc_now()
        self.conn.execute(
            "INSERT OR IGNORE INTO findings(fingerprint,run_id,title,url,parameter,severity,evidence,status,triage_json,first_seen,last_seen) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                fingerprint,
                str(finding.get("run_id", "")),
                title,
                url,
                parameter,
                str(finding.get("severity", "info")),
                str(finding.get("evidence", "")),
                str(finding.get("status", "candidate")),
                json.dumps(finding.get("triage", {}), ensure_ascii=False, sort_keys=True),
                now,
                now,
            ),
        )
        inserted = self.conn.execute("SELECT changes()").fetchone()[0] == 1
        if not inserted:
            self.conn.execute("UPDATE findings SET last_seen=? WHERE fingerprint=?", (now, fingerprint))
        run_id = str(finding.get("run_id", ""))
        if run_id:
            self.conn.execute(
                "INSERT INTO finding_runs(run_id,fingerprint,first_seen,last_seen) VALUES(?,?,?,?) "
                "ON CONFLICT(run_id,fingerprint) DO UPDATE SET last_seen=excluded.last_seen",
                (run_id, fingerprint, now, now),
            )
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM findings WHERE fingerprint=?", (fingerprint,)).fetchone()
        return InsertResult(inserted, fingerprint, int(row[0]))

    def update_finding_triage(self, fingerprint: str, triage: Dict[str, Any], status: str = "triaged") -> None:
        self.conn.execute(
            "UPDATE findings SET triage_json=?,status=?,last_seen=? WHERE fingerprint=?",
            (json.dumps(triage, ensure_ascii=False, sort_keys=True), status, utc_now(), fingerprint),
        )
        self.conn.commit()

    def list_findings(self, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if run_id:
            rows = self.conn.execute(
                "SELECT f.* FROM findings f JOIN finding_runs fr ON fr.fingerprint=f.fingerprint "
                "WHERE fr.run_id=? ORDER BY f.id",
                (run_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM findings ORDER BY id").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if run_id:
                item["run_id"] = run_id
            item["triage"] = json.loads(item.pop("triage_json"))
            result.append(item)
        return result

    def add_evidence(self, finding_fingerprint: str, path: Path, description: str = "") -> str:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        self.conn.execute(
            "INSERT INTO evidence(finding_fingerprint,path,sha256,description,created_at) VALUES(?,?,?,?,?)",
            (finding_fingerprint, str(path), digest, description, utc_now()),
        )
        self.conn.commit()
        return digest

    def evidence_for(self, finding_fingerprint: str) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM evidence WHERE finding_fingerprint=?", (finding_fingerprint,))]

    def save_report(self, run_id: str, path: Path) -> None:
        self.conn.execute(
            "INSERT INTO reports(run_id,path,created_at) VALUES(?,?,?) ON CONFLICT(run_id) DO UPDATE SET path=excluded.path,created_at=excluded.created_at",
            (run_id, str(path), utc_now()),
        )
        self.conn.commit()

    def list_reports(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM reports ORDER BY created_at DESC")]
