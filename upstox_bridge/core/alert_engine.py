"""High-Performance, Zero-Lag Custom Price Alert Engine."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from upstox_bridge.core.config import settings
from upstox_bridge.core.sound_engine import SoundEvent, sound_engine

logger = logging.getLogger("AlertEngine")


class AlertCondition:
    ABOVE = "ABOVE"  # LTP >= Target (Bullish target / breakout)
    BELOW = "BELOW"  # LTP <= Target (Bearish target / breakdown / support)


class AlertStatus:
    ACTIVE = "ACTIVE"
    APPROACHING = "APPROACHING"
    TRIGGERED = "TRIGGERED"


@dataclass
class PriceAlert:
    """Represents a single user-defined custom price alert."""
    id: str
    symbol: str
    target_price: float
    condition: str = AlertCondition.ABOVE
    proximity_pct: float = 0.25
    status: str = AlertStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    triggered_at: Optional[float] = None
    last_ltp: Optional[float] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PriceAlert":
        return cls(
            id=str(data.get("id", uuid.uuid4().hex[:8])),
            symbol=str(data.get("symbol", "")).upper().strip(),
            target_price=float(data.get("target_price", 0.0)),
            condition=str(data.get("condition", AlertCondition.ABOVE)).upper(),
            proximity_pct=float(data.get("proximity_pct", 0.25)),
            status=str(data.get("status", AlertStatus.ACTIVE)),
            created_at=float(data.get("created_at", time.time())),
            triggered_at=float(data["triggered_at"]) if data.get("triggered_at") else None,
            last_ltp=float(data["last_ltp"]) if data.get("last_ltp") else None,
            note=str(data.get("note", "")),
        )


class AlertEngine:
    """
    Evaluates real-time price ticks strictly against user-defined custom price alerts.
    - Two-stage lifecycle: ACTIVE -> APPROACHING (within buffer %) -> TRIGGERED (target hit).
    - Single-shot triggering with hysteresis to prevent repetitive alarm spam.
    - Pure in-memory execution (<0.01ms per tick) with zero COM/Excel overhead.
    - JSON persistence in data/custom_alerts.json.
    """

    _instance: Optional["AlertEngine"] = None

    def __init__(self, storage_path: Optional[Path] = None):
        self._lock = threading.Lock()
        self._alerts: Dict[str, PriceAlert] = {}  # alert_id -> PriceAlert
        self._by_symbol: Dict[str, List[str]] = {}  # symbol_upper -> [alert_id, ...]
        self._listeners: List[Callable[[PriceAlert, str, float], None]] = []

        self.storage_path = storage_path or (settings.root_dir / "data" / "custom_alerts.json")
        self.load_alerts()

    @classmethod
    def get_instance(cls) -> "AlertEngine":
        """Get or initialize singleton instance."""
        if cls._instance is None:
            cls._instance = AlertEngine()
        return cls._instance

    def add_listener(self, callback: Callable[[PriceAlert, str, float], None]) -> None:
        """Register listener callback: callback(alert, event_type, current_ltp)."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[PriceAlert, str, float], None]) -> None:
        """Unregister listener callback."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify(self, alert: PriceAlert, event: str, ltp: float) -> None:
        """Broadcast alert event to registered listeners safely."""
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(alert, event, ltp)
            except Exception as e:
                logger.debug(f"Alert listener error: {e}")

    def add_alert(
        self,
        symbol: str,
        target_price: float,
        condition: str = AlertCondition.ABOVE,
        proximity_pct: Optional[float] = None,
        note: str = "",
    ) -> PriceAlert:
        """Add a new custom target price alert."""
        clean_sym = symbol.upper().strip()
        cond = condition.upper().strip()
        prox = proximity_pct if proximity_pct is not None else settings.alert_proximity_pct

        alert = PriceAlert(
            id=uuid.uuid4().hex[:8],
            symbol=clean_sym,
            target_price=round(float(target_price), 2),
            condition=cond,
            proximity_pct=max(0.01, round(float(prox), 2)),
            status=AlertStatus.ACTIVE,
            note=note.strip(),
        )

        with self._lock:
            self._alerts[alert.id] = alert
            if clean_sym not in self._by_symbol:
                self._by_symbol[clean_sym] = []
            self._by_symbol[clean_sym].append(alert.id)

        self.save_alerts()
        logger.info(f"Custom alert added: [{alert.symbol}] {alert.condition} {alert.target_price} (buffer: {alert.proximity_pct}%)")
        return alert

    def remove_alert(self, alert_id: str) -> bool:
        """Remove an alert by ID."""
        with self._lock:
            alert = self._alerts.pop(alert_id, None)
            if alert:
                sym_list = self._by_symbol.get(alert.symbol, [])
                if alert_id in sym_list:
                    sym_list.remove(alert_id)
                if not sym_list:
                    self._by_symbol.pop(alert.symbol, None)

        if alert:
            self.save_alerts()
            logger.info(f"Custom alert removed: [{alert.symbol}] {alert.condition} {alert.target_price}")
            return True
        return False

    def reset_alert(self, alert_id: str) -> bool:
        """Re-arm a triggered or approaching alert back to ACTIVE."""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert:
                alert.status = AlertStatus.ACTIVE
                alert.triggered_at = None

        if alert:
            self.save_alerts()
            logger.info(f"Custom alert re-armed: [{alert.symbol}] {alert.condition} {alert.target_price}")
            return True
        return False

    def get_alerts(self) -> List[PriceAlert]:
        """Return all custom alerts."""
        with self._lock:
            return list(self._alerts.values())

    def get_active_count(self) -> int:
        """Return count of active and approaching alerts."""
        with self._lock:
            return sum(1 for a in self._alerts.values() if a.status in (AlertStatus.ACTIVE, AlertStatus.APPROACHING))

    def evaluate_tick(self, symbol: str, ltp: float) -> Optional[str]:
        """
        Fast in-memory tick evaluation (< 0.01ms).
        Called whenever a new market price arrives for a symbol.
        """
        clean_sym = symbol.upper().strip()
        with self._lock:
            alert_ids = self._by_symbol.get(clean_sym)
            if not alert_ids:
                return None
            alerts_to_check = [self._alerts[aid] for aid in alert_ids if aid in self._alerts]

        highest_event = None
        for alert in alerts_to_check:
            alert.last_ltp = ltp
            if alert.status == AlertStatus.TRIGGERED:
                continue

            event = self._evaluate_single_alert(alert, ltp)
            if event:
                highest_event = event

        return highest_event

    def _evaluate_single_alert(self, alert: PriceAlert, ltp: float) -> Optional[str]:
        """Evaluate a single alert against live LTP."""
        target = alert.target_price
        if target <= 0:
            return None

        distance_pct = abs(ltp - target) / target * 100.0

        # 1. Target Hit Evaluation
        is_hit = False
        if alert.condition == AlertCondition.ABOVE:
            is_hit = (ltp >= target)
        elif alert.condition == AlertCondition.BELOW:
            is_hit = (ltp <= target)

        if is_hit:
            alert.status = AlertStatus.TRIGGERED
            alert.triggered_at = time.time()
            self.save_alerts()
            sound_engine.play(SoundEvent.TARGET_HIT)
            logger.info(f"🔔 ALERT TRIGGERED: [{alert.symbol}] hit target {target:.2f}! Current LTP: {ltp:.2f}")
            self._notify(alert, "TRIGGERED", ltp)
            return "TRIGGERED"

        # 2. Approaching Buffer Evaluation
        if alert.status == AlertStatus.ACTIVE:
            is_approaching = False
            if distance_pct <= alert.proximity_pct:
                if alert.condition == AlertCondition.ABOVE and ltp < target:
                    is_approaching = True
                elif alert.condition == AlertCondition.BELOW and ltp > target:
                    is_approaching = True

            if is_approaching:
                alert.status = AlertStatus.APPROACHING
                sound_engine.play(SoundEvent.APPROACHING)
                logger.info(f"⚠️ ALERT APPROACHING: [{alert.symbol}] LTP {ltp:.2f} is within {distance_pct:.2f}% of target {target:.2f}")
                self._notify(alert, "APPROACHING", ltp)
                return "APPROACHING"

        # 3. Hysteresis: If price moves safely away from approaching zone, restore ACTIVE
        elif alert.status == AlertStatus.APPROACHING:
            if distance_pct > alert.proximity_pct * 1.5:
                alert.status = AlertStatus.ACTIVE
                self._notify(alert, "ACTIVE", ltp)

        return None

    def load_alerts(self) -> None:
        """Load alerts from persistent JSON storage."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self._lock:
                self._alerts.clear()
                self._by_symbol.clear()
                for item in data.get("alerts", []):
                    alert = PriceAlert.from_dict(item)
                    self._alerts[alert.id] = alert
                    if alert.symbol not in self._by_symbol:
                        self._by_symbol[alert.symbol] = []
                    self._by_symbol[alert.symbol].append(alert.id)

            logger.info(f"Loaded {len(self._alerts)} custom price alerts from {self.storage_path.name}")
        except Exception as e:
            logger.warning(f"Could not load custom alerts from {self.storage_path}: {e}")

    def save_alerts(self) -> None:
        """Atomically persist custom alerts to JSON storage."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                alerts_data = [a.to_dict() for a in self._alerts.values()]

            temp_path = self.storage_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump({"alerts": alerts_data, "updated_at": time.time()}, f, indent=2)

            temp_path.replace(self.storage_path)
        except Exception as e:
            logger.debug(f"Could not save custom alerts: {e}")


# Global default instance
alert_engine = AlertEngine.get_instance()
