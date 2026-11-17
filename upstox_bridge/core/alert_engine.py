"""High-Performance Real-Time 2-Stage Price Alert and Signal Engine."""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from upstox_bridge.core.config import settings
from upstox_bridge.core.sound_engine import SoundEngine, SoundEvent, sound_engine

logger = logging.getLogger("AlertEngine")


class AlertCondition:
    ABOVE = "ABOVE"  # LTP >= Target (Bullish target / breakout)
    BELOW = "BELOW"  # LTP <= Target (Bearish target / breakdown / Stop-Loss)


class AlertStatus:
    ACTIVE = "ACTIVE"
    APPROACHING = "APPROACHING"
    TRIGGERED = "TRIGGERED"
    DISABLED = "DISABLED"


class AlertType:
    CUSTOM = "CUSTOM"
    BST_TGT1 = "BST_TGT1"
    BST_TGT2 = "BST_TGT2"
    BST_TGT3 = "BST_TGT3"
    BST_SL = "BST_SL"


@dataclass
class PriceAlert:
    """Represents a single user-defined or automatic price alert."""
    id: str
    symbol: str
    target_price: float
    condition: str = AlertCondition.ABOVE
    proximity_pct: float = 0.25
    alert_type: str = AlertType.CUSTOM
    status: str = AlertStatus.ACTIVE
    instrument_key: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    triggered_at: Optional[float] = None
    initial_price: Optional[float] = None
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
            alert_type=str(data.get("alert_type", AlertType.CUSTOM)),
            status=str(data.get("status", AlertStatus.ACTIVE)),
            instrument_key=data.get("instrument_key"),
            created_at=float(data.get("created_at", time.time())),
            triggered_at=float(data["triggered_at"]) if data.get("triggered_at") else None,
            initial_price=float(data["initial_price"]) if data.get("initial_price") else None,
            note=str(data.get("note", "")),
        )


class AlertEngine:
    """
    Evaluates real-time price ticks against user alerts and BST sheet targets.
    - Two-stage lifecycle: ACTIVE -> APPROACHING (buffer <= 0.25%) -> TRIGGERED.
    - Hysteresis anti-spam to avoid oscillation alarms.
    - JSON file persistence for custom alerts across restarts.
    - Thread-safe and non-blocking sound dispatch.
    """

    _instance: Optional["AlertEngine"] = None

    def __init__(self, storage_path: Optional[Path] = None):
        self._lock = threading.Lock()
        self._alerts: Dict[str, PriceAlert] = {}  # alert_id -> PriceAlert
        self._bst_alerts: Dict[str, Dict[str, PriceAlert]] = {}  # symbol -> {type -> PriceAlert}
        self._listeners: List[Callable[[PriceAlert, str, float], None]] = []
        self._signal_listeners: List[Callable[[str, str, str], None]] = []
        self._last_signals: Dict[str, Tuple[str, str]] = {}  # symbol -> (super_signal, intra_signal)

        self.storage_path = storage_path or (settings.root_dir / "data" / "price_alerts.json")
        self.load_alerts()

    @classmethod
    def get_instance(cls) -> "AlertEngine":
        if cls._instance is None:
            cls._instance = AlertEngine()
        return cls._instance

    def add_listener(self, callback: Callable[[PriceAlert, str, float], None]) -> None:
        """Register listener callback (alert, transition_event, current_ltp)."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[PriceAlert, str, float], None]) -> None:
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def add_signal_listener(self, callback: Callable[[str, str, str], None]) -> None:
        """Register signal listener (symbol, signal_type, signal_value)."""
        with self._lock:
            if callback not in self._signal_listeners:
                self._signal_listeners.append(callback)

    def _notify_listeners(self, alert: PriceAlert, event: str, ltp: float) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(alert, event, ltp)
            except Exception as e:
                logger.debug(f"Alert listener callback error: {e}")

    def _notify_signal_listeners(self, symbol: str, sig_type: str, sig_val: str) -> None:
        with self._lock:
            listeners = list(self._signal_listeners)
        for cb in listeners:
            try:
                cb(symbol, sig_type, sig_val)
            except Exception as e:
                logger.debug(f"Signal listener callback error: {e}")

    # =========================================================================
    # ALERT CRUD & PERSISTENCE
    # =========================================================================

    def add_alert(
        self,
        symbol: str,
        target_price: float,
        condition: Optional[str] = None,
        proximity_pct: Optional[float] = None,
        note: str = "",
        current_ltp: Optional[float] = None,
    ) -> PriceAlert:
        """Add a custom user-defined price alert."""
        clean_sym = symbol.upper().strip()
        if not clean_sym:
            raise ValueError("Symbol cannot be empty.")
        if target_price <= 0:
            raise ValueError("Target price must be greater than zero.")

        # Auto-detect condition if not explicitly provided
        if not condition:
            if current_ltp and current_ltp > 0:
                condition = AlertCondition.ABOVE if target_price >= current_ltp else AlertCondition.BELOW
            else:
                condition = AlertCondition.ABOVE

        prox = proximity_pct if (proximity_pct is not None and proximity_pct > 0) else settings.alert_proximity_pct
        alert_id = uuid.uuid4().hex[:8]

        # Resolve instrument key for direct fast matching
        resolved_key = None
        try:
            from upstox_bridge.instruments.master import InstrumentMaster
            resolved_key = InstrumentMaster().resolve_symbol(clean_sym)
        except Exception:
            pass

        alert = PriceAlert(
            id=alert_id,
            symbol=clean_sym,
            target_price=round(float(target_price), 2),
            condition=condition.upper(),
            proximity_pct=round(float(prox), 3),
            alert_type=AlertType.CUSTOM,
            status=AlertStatus.ACTIVE,
            instrument_key=resolved_key,
            initial_price=round(float(current_ltp), 2) if current_ltp else None,
            note=note.strip(),
        )

        with self._lock:
            self._alerts[alert_id] = alert
            self._save_alerts_unlocked()

        logger.info(f"Price alert set: [{alert.symbol}] {alert.condition} {alert.target_price} (Buffer: {alert.proximity_pct}%)")
        return alert

    def remove_alert(self, alert_id: str) -> bool:
        """Remove an alert by ID."""
        with self._lock:
            if alert_id in self._alerts:
                del self._alerts[alert_id]
                self._save_alerts_unlocked()
                return True
        return False

    def reset_alert(self, alert_id: str) -> bool:
        """Reset a triggered or approaching alert back to ACTIVE."""
        with self._lock:
            if alert_id in self._alerts:
                self._alerts[alert_id].status = AlertStatus.ACTIVE
                self._alerts[alert_id].triggered_at = None
                self._save_alerts_unlocked()
                return True
        return False

    def clear_triggered_alerts(self) -> int:
        """Clear all triggered alerts."""
        with self._lock:
            to_remove = [aid for aid, a in self._alerts.items() if a.status == AlertStatus.TRIGGERED]
            for aid in to_remove:
                del self._alerts[aid]
            if to_remove:
                self._save_alerts_unlocked()
            return len(to_remove)

    def get_alerts(self) -> List[PriceAlert]:
        """Return list of all custom alerts."""
        with self._lock:
            return list(self._alerts.values())

    def get_active_alerts(self) -> List[PriceAlert]:
        """Return list of all non-triggered custom alerts."""
        with self._lock:
            return [a for a in self._alerts.values() if a.status != AlertStatus.TRIGGERED]

    def load_alerts(self) -> None:
        """Load custom price alerts from JSON file."""
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded: Dict[str, PriceAlert] = {}
            for item in data.get("alerts", []):
                alert = PriceAlert.from_dict(item)
                loaded[alert.id] = alert
            with self._lock:
                self._alerts = loaded
            logger.info(f"Loaded {len(loaded)} saved price alert(s) from {self.storage_path.name}.")
        except Exception as e:
            logger.warning(f"Could not load price alerts from {self.storage_path}: {e}")

    def save_alerts(self) -> None:
        """Thread-safe save to storage."""
        with self._lock:
            self._save_alerts_unlocked()

    def _save_alerts_unlocked(self) -> None:
        """Write custom alerts to disk (caller must hold _lock)."""
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "alerts": [a.to_dict() for a in self._alerts.values()],
        }
        for target_path in (self.storage_path, Path(tempfile.gettempdir()) / "bsa_price_alerts.json"):
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                return
            except Exception:
                continue
        logger.debug("Could not persist price alerts to primary or temp storage.")

    # =========================================================================
    # REAL-TIME EVALUATION
    # =========================================================================

    def evaluate_tick(
        self,
        key_or_symbol: str,
        ltp: float,
        clean_symbol: Optional[str] = None,
    ) -> List[Tuple[PriceAlert, str]]:
        """
        Evaluate an incoming price tick against active alerts.
        Returns list of (alert, event_name) that transitioned.
        """
        if ltp <= 0:
            return []

        target_syms = set()
        clean = (clean_symbol or key_or_symbol).upper().strip()
        target_syms.add(clean)

        # Normalize symbol (strip exchange prefixes like 'NSE_EQ|' or 'NSE_INDEX|')
        if "|" in clean:
            target_syms.add(clean.split("|", 1)[1])
        if "|" in key_or_symbol:
            target_syms.add(key_or_symbol.split("|", 1)[1].upper().strip())
            try:
                from upstox_bridge.instruments.master import InstrumentMaster
                ts = InstrumentMaster().get_symbol_by_key(key_or_symbol)
                if ts:
                    target_syms.add(ts.upper().strip())
            except Exception:
                pass
        target_syms.add(key_or_symbol.upper().strip())

        transitions: List[Tuple[PriceAlert, str]] = []

        with self._lock:
            # Collect matching alerts: both custom alerts and active BST sheet alerts
            candidates: List[PriceAlert] = []
            for alert in self._alerts.values():
                if alert.instrument_key == key_or_symbol or alert.symbol in target_syms or any(s.startswith(alert.symbol) for s in target_syms):
                    candidates.append(alert)

            if settings.alert_auto_bst_enabled:
                for sym_match in target_syms:
                    if sym_match in self._bst_alerts:
                        candidates.extend(self._bst_alerts[sym_match].values())

            for alert in candidates:
                event = self._eval_single_alert(alert, ltp)
                if event:
                    transitions.append((alert, event))

            if any(evt == "TRIGGERED" for _, evt in transitions):
                self._save_alerts_unlocked()

        # Fire callbacks and sounds outside lock
        for alert, event in transitions:
            self._notify_listeners(alert, event, ltp)

        return transitions

    def _eval_single_alert(self, alert: PriceAlert, ltp: float) -> Optional[str]:
        """
        Evaluate a single alert against live LTP. Caller holds _lock.
        Returns 'TRIGGERED', 'APPROACHING', or None.
        """
        if alert.status == AlertStatus.TRIGGERED or alert.status == AlertStatus.DISABLED:
            return None

        distance_pct = abs(ltp - alert.target_price) / alert.target_price * 100.0

        # 1. Check if TARGET IS HIT
        target_reached = False
        if alert.condition == AlertCondition.ABOVE and ltp >= alert.target_price:
            target_reached = True
        elif alert.condition == AlertCondition.BELOW and ltp <= alert.target_price:
            target_reached = True

        if target_reached:
            alert.status = AlertStatus.TRIGGERED
            alert.triggered_at = time.time()

            # Play corresponding alert bell
            if alert.alert_type == AlertType.BST_SL:
                sound_engine.play(SoundEvent.STOP_LOSS)
            else:
                sound_engine.play(SoundEvent.TARGET_HIT)

            logger.info(f"🎯 ALERT HIT: [{alert.symbol}] {alert.condition} {alert.target_price} reached at LTP {ltp}")
            return "TRIGGERED"

        # 2. Check if APPROACHING within proximity buffer
        if alert.status == AlertStatus.ACTIVE:
            is_approaching = False
            if distance_pct <= alert.proximity_pct:
                # Must be approaching from the pending direction
                if alert.condition == AlertCondition.ABOVE and ltp < alert.target_price:
                    is_approaching = True
                elif alert.condition == AlertCondition.BELOW and ltp > alert.target_price:
                    is_approaching = True

            if is_approaching:
                alert.status = AlertStatus.APPROACHING
                sound_engine.play(SoundEvent.APPROACHING)
                logger.info(f"⚠️ ALERT APPROACHING: [{alert.symbol}] LTP {ltp} is {distance_pct:.2f}% from {alert.target_price}")
                return "APPROACHING"

        # 3. Hysteresis Reset: If price moves away from target, restore ACTIVE
        elif alert.status == AlertStatus.APPROACHING:
            if distance_pct > alert.proximity_pct * 1.5:
                # Price pulled back safely outside buffer
                alert.status = AlertStatus.ACTIVE

        return None

    # =========================================================================
    # BST SHEET TARGET & SIGNAL MONITORING
    # =========================================================================

    def update_bst_targets(
        self,
        symbol: str,
        entry: Optional[float] = None,
        sl: Optional[float] = None,
        tgt1: Optional[float] = None,
        tgt2: Optional[float] = None,
        tgt3: Optional[float] = None,
    ) -> None:
        """Update or register auto-monitored targets from BST Excel sheet."""
        if not settings.alert_auto_bst_enabled:
            return

        clean = symbol.upper().strip()
        if not clean:
            return

        with self._lock:
            if clean not in self._bst_alerts:
                self._bst_alerts[clean] = {}

            def _sync_bst_alert(alert_type: str, price: Optional[float], condition: str, note: str):
                if price is not None and price > 0:
                    current = self._bst_alerts[clean].get(alert_type)
                    if not current:
                        self._bst_alerts[clean][alert_type] = PriceAlert(
                            id=f"bst_{clean}_{alert_type}",
                            symbol=clean,
                            target_price=round(float(price), 2),
                            condition=condition,
                            proximity_pct=settings.alert_proximity_pct,
                            alert_type=alert_type,
                            status=AlertStatus.ACTIVE,
                            note=note,
                        )
                    elif current.target_price != round(float(price), 2):
                        # Target updated in sheet
                        current.target_price = round(float(price), 2)
                        current.status = AlertStatus.ACTIVE
                        current.triggered_at = None

            _sync_bst_alert(AlertType.BST_SL, sl, AlertCondition.BELOW, "BST Stop-Loss")
            _sync_bst_alert(AlertType.BST_TGT1, tgt1, AlertCondition.ABOVE, "BST Target 1")
            _sync_bst_alert(AlertType.BST_TGT2, tgt2, AlertCondition.ABOVE, "BST Target 2")
            _sync_bst_alert(AlertType.BST_TGT3, tgt3, AlertCondition.ABOVE, "BST Target 3")

    def evaluate_signal_change(
        self,
        symbol: str,
        super_sig: Optional[str] = None,
        intra_sig: Optional[str] = None,
    ) -> None:
        """Evaluate BST SUPER and INTRA signals and trigger chimes on flips."""
        if not settings.sound_signals_enabled:
            return

        clean = symbol.upper().strip()
        if not clean:
            return

        clean_super = str(super_sig or "").strip().upper()
        clean_intra = str(intra_sig or "").strip().upper()

        with self._lock:
            prev_super, prev_intra = self._last_signals.get(clean, ("", ""))
            self._last_signals[clean] = (clean_super, clean_intra)

        # 1. SUPER Signal Flip
        if clean_super and clean_super != prev_super:
            if "BUY" in clean_super:
                sound_engine.play(SoundEvent.SIGNAL_BUY)
                logger.info(f"🟢 [SUPER SIGNAL] {clean} -> BUY")
                self._notify_signal_listeners(clean, "SUPER", "BUY")
            elif "SELL" in clean_super:
                sound_engine.play(SoundEvent.SIGNAL_SELL)
                logger.info(f"🔴 [SUPER SIGNAL] {clean} -> SELL")
                self._notify_signal_listeners(clean, "SUPER", "SELL")

        # 2. INTRA Signal Flip
        if clean_intra and clean_intra != prev_intra:
            if "BUY" in clean_intra:
                sound_engine.play(SoundEvent.SIGNAL_BUY)
                logger.info(f"🟢 [INTRA SIGNAL] {clean} -> BUY")
                self._notify_signal_listeners(clean, "INTRA", "BUY")
            elif "SELL" in clean_intra:
                sound_engine.play(SoundEvent.SIGNAL_SELL)
                logger.info(f"🔴 [INTRA SIGNAL] {clean} -> SELL")
                self._notify_signal_listeners(clean, "INTRA", "SELL")


# Global default instance
alert_engine = AlertEngine.get_instance()
