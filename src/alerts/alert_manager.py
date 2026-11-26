"""Central alert management system for traffic events."""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from enum import Enum


class AlertType(Enum):
    ACCIDENT = "accident"
    HEAVY_TRAFFIC = "heavy_traffic"
    ILLEGAL_VEHICLE = "illegal_vehicle"
    EMERGENCY_VEHICLE = "emergency_vehicle"
    SIGNAL_OVERRIDE = "signal_override"


class AlertPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Alert:
    """A system alert to be dispatched."""
    alert_id: str
    alert_type: AlertType
    priority: AlertPriority
    title: str
    message: str
    timestamp: float = 0.0
    location: str = ""
    camera_id: str = ""
    is_sent: bool = False
    sent_via: List[str] = field(default_factory=list)  # "sms", "app", "email"
    metadata: Dict = field(default_factory=dict)


class AlertManager:
    """Manages and dispatches alerts through configured channels.

    Supports:
    - SMS via Twilio
    - App push notifications
    - In-app dashboard alerts
    - Configurable alert rules and thresholds
    """

    def __init__(
        self,
        sms_enabled: bool = False,
        notification_enabled: bool = True,
        min_priority: AlertPriority = AlertPriority.MEDIUM,
        cooldown_seconds: float = 30.0,
    ):
        self.sms_enabled = sms_enabled
        self.notification_enabled = notification_enabled
        self.min_priority = min_priority
        self.cooldown_seconds = cooldown_seconds

        self._alert_counter = 0
        self._alerts: List[Alert] = []
        self._last_alert_time: Dict[str, float] = {}  # type -> last_sent_time
        self._sms_sender = None
        self._notification_sender = None
        self._subscribers: List[Callable[[Alert], None]] = []

    def set_sms_sender(self, sender):
        """Attach an SMSSender instance."""
        self._sms_sender = sender
        self.sms_enabled = True

    def set_notification_sender(self, sender):
        """Attach a NotificationSender instance."""
        self._notification_sender = sender
        self.notification_enabled = True

    def subscribe(self, callback: Callable[[Alert], None]):
        """Register a callback for real-time alert notifications."""
        self._subscribers.append(callback)

    def create_alert(
        self,
        alert_type: AlertType,
        priority: AlertPriority,
        title: str,
        message: str,
        location: str = "",
        camera_id: str = "",
        metadata: Dict = None,
    ) -> Optional[Alert]:
        """Create and dispatch an alert if it meets threshold and cooldown.

        Returns:
            Alert object if created, None if suppressed by cooldown/priority.
        """
        # Priority check
        if priority.value < self.min_priority.value:
            return None

        # Cooldown check per alert type
        current_time = time.time()
        type_key = alert_type.value
        if type_key in self._last_alert_time:
            if current_time - self._last_alert_time[type_key] < self.cooldown_seconds:
                return None

        self._alert_counter += 1
        alert = Alert(
            alert_id=f"ALT_{self._alert_counter:05d}",
            alert_type=alert_type,
            priority=priority,
            title=title,
            message=message,
            timestamp=current_time,
            location=location,
            camera_id=camera_id,
            metadata=metadata or {},
        )

        # Dispatch through channels
        self._dispatch(alert)

        self._alerts.append(alert)
        self._last_alert_time[type_key] = current_time

        # Keep only last 500 alerts
        if len(self._alerts) > 500:
            self._alerts = self._alerts[-500:]

        return alert

    def _dispatch(self, alert: Alert):
        """Send alert through all configured channels."""
        # SMS
        if self.sms_enabled and self._sms_sender and alert.priority.value >= AlertPriority.HIGH.value:
            try:
                self._sms_sender.send(alert)
                alert.sent_via.append("sms")
            except Exception:
                pass

        # Push notification
        if self.notification_enabled and self._notification_sender:
            try:
                self._notification_sender.send(alert)
                alert.sent_via.append("app")
            except Exception:
                pass

        # In-app subscribers
        for callback in self._subscribers:
            try:
                callback(alert)
            except Exception:
                pass

        alert.is_sent = True

    def get_alerts(
        self,
        last_n: int = 50,
        alert_type: Optional[AlertType] = None,
        min_priority: Optional[AlertPriority] = None,
    ) -> List[Alert]:
        """Get recent alerts with optional filters."""
        filtered = self._alerts
        if alert_type:
            filtered = [a for a in filtered if a.alert_type == alert_type]
        if min_priority:
            filtered = [a for a in filtered if a.priority.value >= min_priority.value]
        return filtered[-last_n:]

    def get_alert_stats(self) -> Dict:
        """Get alert statistics."""
        stats = {"total": len(self._alerts)}
        for at in AlertType:
            type_alerts = [a for a in self._alerts if a.alert_type == at]
            stats[at.value] = len(type_alerts)
        return stats

    def clear(self):
        self._alerts.clear()
        self._alert_counter = 0
        self._last_alert_time.clear()
