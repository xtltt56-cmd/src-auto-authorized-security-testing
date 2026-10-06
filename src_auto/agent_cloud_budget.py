"""Conservative, durable DeepSeek reservations; reuse the project spend ledger.

Reservations are intentionally not refunded on timeout, restart, or cancellation:
an in-flight request can still be billed. They are budget estimates, not invoices.
"""
import math
from datetime import datetime, timezone

from .config import load_mapping
from .provider_credentials import OFFICIAL_ENDPOINTS
from .store import Store, utc_now

CALL_TOKEN_RESERVATION = 8000


class DeepSeekAgentBudget:
    def __init__(self, root, config, provider, policy):
        if (config.get("cloud_enabled") is not True or not provider.get("enabled")
                or provider.get("manual_only") is not True or provider.get("model") != "deepseek-flash"
                or provider.get("endpoint") != OFFICIAL_ENDPOINTS["deepseek"]):
            raise ValueError("cloud_agent_not_validated")
        self.root = root
        self.input_rate = self._number(config.get("peak_input_cny_per_million"), positive=True)
        self.output_rate = self._number(config.get("peak_output_cny_per_million"), positive=True)
        self.daily = self._number(policy.get("daily_ai_budget_yuan", 10))
        self.monthly = self._number(policy.get("monthly_ai_budget_yuan", 100))
        self.call_reservation = round(CALL_TOKEN_RESERVATION * max(self.input_rate, self.output_rate) / 1000000, 8)

    @staticmethod
    def _number(value, positive=False):
        if isinstance(value, bool): raise ValueError("invalid_cloud_budget")
        try: number = float(value)
        except (TypeError, ValueError): raise ValueError("invalid_cloud_budget") from None
        if not math.isfinite(number) or number < 0 or (positive and number == 0):
            raise ValueError("invalid_cloud_budget")
        return number

    @classmethod
    def configured(cls, root):
        models = load_mapping(root / "config/models.yaml")
        return cls(root, models.get("agent", {}), models.get("remote_providers", {}).get("deepseek", {}),
                   load_mapping(root / "config/policy.yaml"))

    def reserve(self, run_id):
        now = datetime.now().astimezone()
        day = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
        month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
        store = Store(self.root / "data/src_auto.sqlite3")
        try:
            with store.conn:
                store.conn.execute("BEGIN IMMEDIATE")
                def spent(start):
                    return self._number(store.conn.execute("SELECT COALESCE(SUM(amount),0) FROM spend WHERE created_at>=?", (start,)).fetchone()[0])
                if spent(day) + self.call_reservation > self.daily or spent(month) + self.call_reservation > self.monthly:
                    raise RuntimeError("cloud_budget_limit")
                store.conn.execute("INSERT INTO spend(amount,category,run_id,created_at) VALUES(?,?,?,?)",
                                   (self.call_reservation, "agent_deepseek_reserved", run_id, utc_now()))
            return self.call_reservation
        finally:
            store.close()

    def estimate(self, input_tokens, output_tokens, estimated):
        if estimated: return self.call_reservation
        return round((input_tokens * self.input_rate + output_tokens * self.output_rate) / 1000000, 8)
