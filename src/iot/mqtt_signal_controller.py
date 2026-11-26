"""IoT Traffic Signal Controller using MQTT protocol.

Controls real traffic signal hardware via MQTT messages.
Compatible with Raspberry Pi + Relay modules, Arduino, ESP32.

Hardware Setup (Raspberry Pi):
    - Raspberry Pi 3/4
    - 4-channel relay module (for 4-way intersection)
    - Red, Yellow, Green LEDs or actual signal lights
    - MQTT broker (Mosquitto) running on Pi or server

MQTT Topics:
    - traffic/signal/{direction}/state  → "red", "yellow", "green"
    - traffic/signal/emergency          → emergency override messages
    - traffic/signal/status             → current status request/response
"""

import os
import json
import time
from typing import Dict, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class SignalHardwareState:
    """Physical signal state at a junction."""
    direction: str
    state: str  # "red", "yellow", "green"
    gpio_red: int = 0
    gpio_yellow: int = 0
    gpio_green: int = 0
    last_changed: float = 0.0


class MQTTSignalController:
    """Controls physical traffic signals via MQTT protocol.

    In production, this sends MQTT messages to Raspberry Pi controllers
    at each intersection. Each Pi controls relay modules connected to
    the actual traffic signal lights.

    For demo/testing, it simulates the hardware locally.
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        topic_prefix: str = "traffic/signal",
        simulate: bool = True,
    ):
        self.broker_host = broker_host or os.getenv("MQTT_BROKER_HOST", "localhost")
        self.broker_port = broker_port
        self.username = username or os.getenv("MQTT_USERNAME", "")
        self.password = password or os.getenv("MQTT_PASSWORD", "")
        self.topic_prefix = topic_prefix
        self.simulate = simulate

        self._client = None
        self._connected = False
        self._signal_states: Dict[str, SignalHardwareState] = {}
        self._change_log = []

        # Initialize 4-way intersection signals
        # GPIO pin assignments (BCM numbering for Raspberry Pi)
        gpio_map = {
            "north": {"red": 17, "yellow": 27, "green": 22},
            "south": {"red": 23, "yellow": 24, "green": 25},
            "east": {"red": 5, "yellow": 6, "green": 13},
            "west": {"red": 16, "yellow": 20, "green": 21},
        }

        for direction, pins in gpio_map.items():
            self._signal_states[direction] = SignalHardwareState(
                direction=direction,
                state="red",
                gpio_red=pins["red"],
                gpio_yellow=pins["yellow"],
                gpio_green=pins["green"],
            )

        if not simulate:
            self._connect_mqtt()

    def _connect_mqtt(self):
        """Connect to MQTT broker."""
        try:
            import paho.mqtt.client as mqtt

            self._client = mqtt.Client(client_id="traffic_controller")

            if self.username:
                self._client.username_pw_set(self.username, self.password)

            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    self._connected = True
                    logger.info(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}")
                    client.subscribe(f"{self.topic_prefix}/status/request")
                else:
                    logger.error(f"MQTT connection failed with code {rc}")

            def on_message(client, userdata, msg):
                if msg.topic.endswith("/status/request"):
                    self._publish_full_status()

            self._client.on_connect = on_connect
            self._client.on_message = on_message
            self._client.connect(self.broker_host, self.broker_port, 60)
            self._client.loop_start()

        except ImportError:
            logger.warning("paho-mqtt package not installed. Using simulation mode.")
            self.simulate = True
        except Exception as e:
            logger.error(f"MQTT connection error: {e}. Falling back to simulation.")
            self.simulate = True

    def set_signal(self, direction: str, state: str):
        """Set a traffic signal to a specific state.

        Args:
            direction: "north", "south", "east", "west"
            state: "red", "yellow", "green"
        """
        if direction not in self._signal_states:
            logger.warning(f"Unknown direction: {direction}")
            return

        old_state = self._signal_states[direction].state
        self._signal_states[direction].state = state
        self._signal_states[direction].last_changed = time.time()

        log_entry = {
            "timestamp": time.time(),
            "direction": direction,
            "old_state": old_state,
            "new_state": state,
        }
        self._change_log.append(log_entry)
        if len(self._change_log) > 200:
            self._change_log = self._change_log[-200:]

        if self.simulate:
            logger.info(f"[SIMULATED] Signal {direction}: {old_state} → {state}")
        else:
            self._publish_signal(direction, state)

    def set_emergency_override(self, green_direction: str, duration: float = 30.0):
        """Emergency override: set one direction GREEN, all others RED.

        Args:
            green_direction: Direction to turn green.
            duration: How long to hold the override (seconds).
        """
        for direction in self._signal_states:
            if direction == green_direction:
                self.set_signal(direction, "green")
            else:
                self.set_signal(direction, "red")

        if not self.simulate and self._client and self._connected:
            payload = json.dumps({
                "type": "emergency_override",
                "green_direction": green_direction,
                "duration": duration,
                "timestamp": time.time(),
            })
            self._client.publish(f"{self.topic_prefix}/emergency", payload)

        logger.info(f"Emergency override: {green_direction} → GREEN for {duration}s")

    def set_normal_cycle(self, green_direction: str):
        """Set normal traffic cycle with one direction green."""
        for direction in self._signal_states:
            if direction == green_direction:
                self.set_signal(direction, "green")
            else:
                self.set_signal(direction, "red")

    def _publish_signal(self, direction: str, state: str):
        """Publish signal state change via MQTT."""
        if self._client and self._connected:
            topic = f"{self.topic_prefix}/{direction}/state"
            payload = json.dumps({
                "direction": direction,
                "state": state,
                "timestamp": time.time(),
            })
            self._client.publish(topic, payload, retain=True)

    def _publish_full_status(self):
        """Publish current status of all signals."""
        if self._client and self._connected:
            status = self.get_all_states()
            self._client.publish(
                f"{self.topic_prefix}/status/response",
                json.dumps(status),
            )

    def get_all_states(self) -> Dict[str, Dict]:
        """Get current state of all signals."""
        return {
            direction: {
                "state": sig.state,
                "gpio_pins": {
                    "red": sig.gpio_red,
                    "yellow": sig.gpio_yellow,
                    "green": sig.gpio_green,
                },
                "last_changed": sig.last_changed,
            }
            for direction, sig in self._signal_states.items()
        }

    def get_change_log(self, last_n: int = 20) -> list:
        return self._change_log[-last_n:]

    def disconnect(self):
        """Disconnect from MQTT broker."""
        if self._client and self._connected:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected or self.simulate
