"""Optional local Broker smoke using a unique virtual device and temporary database.

Run: python -m tests.mqtt_control_smoke --host 127.0.0.1 --port 1883
"""

import argparse
import json
import tempfile
import threading
import uuid
from datetime import timedelta
from pathlib import Path

import paho.mqtt.client as mqtt

from iot_control.mqtt import ControlMQTT
from iot_control.repository import ControlRepository, utc_now


def run(host: str, port: int) -> None:
    device_id = "tool-smoke-" + uuid.uuid4().hex
    received = threading.Event()
    subscribed = threading.Event()
    control_ready = threading.Event()
    subscriptions = []
    with tempfile.TemporaryDirectory() as directory:
        repo = ControlRepository(str(Path(directory) / "control.db"))
        control = ControlMQTT(repo)
        # The production client ID must remain connected. Use an isolated smoke client.
        control.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=device_id + "-control")
        control.client.on_connect = control._on_connect
        control.client.on_message = control._on_message

        def on_control_subscribe(client, userdata, mid, reasons, properties):
            subscriptions.append(mid)
            if len(subscriptions) == 4:
                control_ready.set()

        control.client.on_subscribe = on_control_subscribe
        device = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=device_id + "-device")
        device.on_subscribe = lambda *_: subscribed.set()

        def on_command(client, userdata, message):
            payload = json.loads(message.payload)
            client.publish(f"iot/{device_id}/cmd_ack", json.dumps({
                "command_id": payload["command_id"], "status": "applied",
            }), qos=1)
            client.publish(f"iot/{device_id}/status", json.dumps({
                "online": True, "mqtt_status": "connected",
            }), qos=1)

        device.on_message = on_command
        original = repo.record_status_sample

        def observed(device_name, payload):
            original(device_name, payload)
            if device_name == device_id:
                received.set()

        repo.record_status_sample = observed
        try:
            control.client.connect(host, port)
            control.client.loop_start()
            device.connect(host, port)
            device.loop_start()
            device.subscribe(f"iot/{device_id}/cmd", qos=1)
            assert subscribed.wait(5), "virtual device subscription failed"
            assert control_ready.wait(5), "control subscriptions failed"
            command = repo.create_command(device_id, "reconnect_mqtt", "low", "DIA_20261007_DEADBEEF")
            result = repo.dispatch_command(command["command_id"], control.send_command)
            assert result["delivery_status"] in {"broker_confirmed", "device_acked"}
            assert received.wait(5), "device status not received"
            assert repo.get_command(command["command_id"])["status"] == "applied"
            results = repo.finalize_watches(utc_now() + timedelta(minutes=2))
            assert results[0]["verify_status"] == "succeeded"
            print("MQTT smoke passed: PUBACK, device ACK, action evidence and persisted verification")
        finally:
            device.disconnect()
            device.loop_stop()
            control.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    options = parser.parse_args()
    run(options.host, options.port)
