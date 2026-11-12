"""Delivery ambiguity, durable observations and action-specific acceptance."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import pytest

from common.migrations import SQLiteMigrationRunner
from iot_control.mqtt import ControlMQTT
from iot_control.repository import ControlRepository, iso, utc_now

DIA = "DIA_20260922_DEADBEEF"


@pytest.fixture
def repo(tmp_path):
    return ControlRepository(str(tmp_path / "control.db"))


@pytest.mark.parametrize("action,parameters,state,baseline", [
    ("reconnect_mqtt", {}, {"mqtt_status": "connected"}, {}),
    ("reconnect_wifi", {}, {"wifi_status": "connected", "rssi": -55}, {}),
    ("calibrate_sensor", {}, {"sensor_valid": True, "sensor_calibrated": True, "temperature": 25}, {}),
    ("set_reporting_interval", {"seconds": 10}, {"reporting_interval_seconds": 10}, {}),
    ("restart_device", {}, {"uptime": 5}, {"uptime": 1000}),
    ("update_firmware", {"version": "2.0"}, {"firmware_version": "2.0"}, {}),
    ("set_mqtt_keepalive", {"seconds": 120},
     {"mqtt_keepalive_seconds": 120, "mqtt_status": "connected"}, {}),
    ("rollback_firmware", {}, {"firmware_version": "1.3.1"},
     {"firmware_version": "1.4.0", "rollback_version": "1.3.1"}),
])
def test_action_requires_its_own_evidence(repo, action, parameters, state, baseline):
    first = repo.create_command("D1", action, "low", DIA, parameters,
                                verification_baseline=baseline)
    second = repo.create_command("D1", action, "low", DIA, parameters,
                                 verification_baseline=baseline)
    for command in (first, second):
        repo.mark_command_ack(command["command_id"], "applied", {})
    repo.record_status_sample("D1", {"online": True})
    # Persisted windows survive process restart; both commands remain tracked.
    restarted = ControlRepository(repo.path)
    result = restarted.finalize_watches(utc_now() + timedelta(minutes=2))
    assert len(result) == 2 and all(item["verify_status"] == "inconclusive" for item in result)
    third = restarted.create_command("D1", action, "low", DIA, parameters,
                                     verification_baseline=baseline)
    restarted.mark_command_ack(third["command_id"], "applied", {})
    restarted.record_status_sample("D1", {"online": True, **state})
    restarted = ControlRepository(repo.path)
    assert restarted.finalize_watches(utc_now() + timedelta(minutes=2))[0]["verify_status"] == "succeeded"


@pytest.mark.parametrize("action,parameters,state", [
    ("reconnect_mqtt", {}, {"mqtt_status": "disconnected"}),
    ("reconnect_wifi", {}, {"wifi_status": "connected", "rssi": -90}),
    ("calibrate_sensor", {}, {"sensor_valid": False, "sensor_calibrated": True, "temperature": 78}),
    ("set_reporting_interval", {"seconds": 10}, {"reporting_interval_seconds": 30}),
    ("restart_device", {}, {"uptime": 1500}),
    ("update_firmware", {"version": "2.0"}, {"firmware_version": "1.0"}),
])
def test_online_device_with_unmet_criteria_fails(repo, action, parameters, state):
    command = repo.create_command("D1", action, "low", DIA, parameters,
                                  verification_baseline={"uptime": 1000})
    repo.mark_command_ack(command["command_id"], "applied", {})
    repo.record_status_sample("D1", {"online": True, **state})
    assert repo.finalize_watches(utc_now() + timedelta(minutes=2))[0]["verify_status"] == "failed"


@pytest.mark.parametrize("baseline,state,expected", [
    # 回退后仍在运行原版本：明确失败
    ({"firmware_version": "1.4.0", "rollback_version": "1.3.1"}, {"firmware_version": "1.4.0"}, "failed"),
    # 执行前没有可回退版本，无法判定回退到了哪里
    ({"firmware_version": "1.4.0"}, {"firmware_version": "1.3.1"}, "inconclusive"),
])
def test_rollback_is_judged_against_the_version_offered_before(repo, baseline, state, expected):
    command = repo.create_command("D1", "rollback_firmware", "high", DIA, {},
                                  verification_baseline=baseline)
    repo.mark_command_ack(command["command_id"], "applied", {})
    repo.record_status_sample("D1", {"online": True, **state})
    assert repo.finalize_watches(utc_now() + timedelta(minutes=2))[0]["verify_status"] == expected


def test_keepalive_change_needs_a_connected_session(repo):
    command = repo.create_command("D1", "set_mqtt_keepalive", "low", DIA, {"seconds": 120})
    repo.mark_command_ack(command["command_id"], "applied", {})
    repo.record_status_sample("D1", {"online": True, "mqtt_keepalive_seconds": 120,
                                     "mqtt_status": "disconnected"})
    assert repo.finalize_watches(utc_now() + timedelta(minutes=2))[0]["verify_status"] == "failed"


def test_stale_retained_or_wrong_device_messages_cannot_verify(repo):
    command = repo.create_command("D1", "reconnect_mqtt", "low", DIA)
    assert repo.mark_command_ack(command["command_id"], "applied", {}, device_id="D2") is None
    repo.mark_command_ack(command["command_id"], "applied", {}, device_id="D1")
    client = ControlMQTT(repo)
    state = {"online": True, "mqtt_status": "connected"}
    client._on_message(None, None, SimpleNamespace(topic="iot/D1/status", retain=True,
                                                  payload=json.dumps(state).encode()))
    repo.record_status_sample("D1", {**state, "timestamp": iso(utc_now() - timedelta(minutes=1))})
    repo.record_status_sample("D1", {**state, "timestamp": "invalid"})
    repo.record_status_sample("D1", {**state, "timestamp": iso(utc_now() + timedelta(days=1))})
    repo.record_log_sample("D1", "ERROR", {"timestamp": iso(utc_now() - timedelta(minutes=1))})
    assert repo.finalize_watches(utc_now() + timedelta(minutes=2))[0]["verify_status"] == "inconclusive"


def test_cleared_retained_message_is_ignored_without_error(repo, caplog):
    client = ControlMQTT(repo)
    with caplog.at_level("ERROR", logger="xiaoyi.iot_control.mqtt"):
        for kind in ("cmd_ack", "status", "logs", "fault"):
            client._on_message(None, None, SimpleNamespace(topic=f"iot/D1/{kind}", retain=False, payload=b""))
    assert caplog.records == []


def test_newer_failure_is_not_overwritten_by_older_success(repo):
    command = repo.create_command("D1", "reconnect_mqtt", "low", DIA)
    repo.mark_command_ack(command["command_id"], "applied", {})
    older = iso()
    repo.record_status_sample("D1", {"online": True, "mqtt_status": "disconnected", "timestamp": iso()})
    repo.record_status_sample("D1", {"online": True, "mqtt_status": "connected", "timestamp": older})
    assert repo.finalize_watches(utc_now() + timedelta(minutes=2))[0]["verify_status"] == "failed"


def test_delivery_claim_is_single_and_unknown_is_never_retried(repo):
    command = repo.create_command("D1", "restart_device", "high", DIA)
    sent = []

    def send(device, item):
        sent.append(item["command_id"])
        return "unknown"

    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(lambda _: repo.dispatch_command(command["command_id"], send), range(2)))
    ControlRepository(repo.path).dispatch_pending(send)
    assert sent == [command["command_id"]]
    assert repo.get_command(command["command_id"])["delivery_status"] == "unknown"


def test_ack_arriving_during_publish_is_not_overwritten(repo):
    command = repo.create_command("D1", "reconnect_mqtt", "low", DIA)

    def send(device, item):
        repo.mark_command_ack(item["command_id"], "applied", {}, device_id=device)
        return "broker_confirmed"

    result = repo.dispatch_command(command["command_id"], send)
    assert result["status"] == "applied" and result["delivery_status"] == "device_acked"


def test_firmware_update_waits_longer_for_its_ack(repo):
    """OTA 回执要等镜像下载并校验完，30 秒的通用超时不适用。"""
    def sent(command, seconds_ago):
        repo.dispatch_command(command["command_id"], lambda *_: "broker_confirmed")
        with repo._connect() as db:
            db.execute("UPDATE command_outbox SET confirmed_at = ? WHERE command_id = ?",
                       (iso(utc_now() - timedelta(seconds=seconds_ago)), command["command_id"]))

    update = repo.create_command("D1", "update_firmware", "high", DIA, {"version": "1.3.9"})
    reconnect = repo.create_command("D2", "reconnect_mqtt", "low", DIA)
    sent(update, 120)
    sent(reconnect, 120)
    assert repo.mark_timed_out_commands() == [reconnect["command_id"]]
    # 迟到的 OTA 回执仍被接受并进入验证
    assert repo.mark_command_ack(update["command_id"], "applied", {}, device_id="D1")["status"] == "applied"

    late = repo.create_command("D3", "update_firmware", "high", DIA, {"version": "1.3.9"})
    sent(late, 301)
    assert repo.mark_timed_out_commands() == [late["command_id"]]


def test_unsent_command_does_not_use_ack_timeout_but_expires(repo):
    command = repo.create_command("D1", "restart_device", "high", DIA)
    with repo._connect() as db:
        db.execute("UPDATE device_command SET created_at = ? WHERE command_id = ?",
                   (iso(utc_now() - timedelta(minutes=5)), command["command_id"]))
    assert repo.mark_timed_out_commands() == []
    with repo._connect() as db:
        db.execute("UPDATE command_outbox SET expires_at = ? WHERE command_id = ?",
                   (iso(utc_now() - timedelta(seconds=1)), command["command_id"]))
    repo.dispatch_pending(lambda *_: pytest.fail("expired command published"))
    assert repo.mark_timed_out_commands() == [command["command_id"]]


def test_crash_during_publish_becomes_unknown(repo):
    command = repo.create_command("D1", "restart_device", "high", DIA)
    with repo._connect() as db:
        db.execute("UPDATE command_outbox SET delivery_status = 'dispatching' WHERE command_id = ?",
                   (command["command_id"],))
    restarted = ControlRepository(repo.path)
    restarted.recover_delivery()
    restarted.dispatch_pending(lambda *_: pytest.fail("ambiguous command resent"))
    assert restarted.get_command(command["command_id"])["delivery_status"] == "unknown"


def test_existing_commands_are_not_queued_on_migration(tmp_path):
    path = str(tmp_path / "legacy.db")
    runner = ControlRepository.migration_runner()
    SQLiteMigrationRunner(runner.migrations[:4], service="iot_control").upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("""INSERT INTO device_command
            (command_id, device_id, action, risk_level, diagnosis_id, status, created_at, updated_at)
            VALUES ('OLD', 'D1', 'restart_device', 'high', ?, 'applied', ?, ?)""", (DIA, iso(), iso()))
        db.execute("""INSERT INTO device_command
            (command_id, device_id, action, risk_level, diagnosis_id, status, created_at, updated_at)
            VALUES ('INFLIGHT', 'D1', 'restart_device', 'high', ?, 'pending', ?, ?)""", (DIA, iso(), iso()))
    runner.upgrade(path)
    repo = ControlRepository(path)
    repo.dispatch_pending(lambda *_: pytest.fail("legacy command resent"))
    assert repo.mark_timed_out_commands() == []
    assert repo.get_command("OLD")["delivery_status"] == "unknown"
    assert repo.finalize_watches(utc_now() + timedelta(minutes=2))[0]["verify_status"] == "inconclusive"


def test_database_connections_close_at_context_exit(repo):
    with repo._connect() as connection:
        connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
    with repo.migration_runner()._connect(repo.path) as connection:
        connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


@pytest.mark.parametrize("connected,rc,published,expected", [
    (False, 0, False, "pending"), (True, 0, True, "broker_confirmed"),
    (True, 0, False, "unknown"), (True, 4, False, "unknown"),
])
def test_mqtt_delivery_requires_puback(repo, connected, rc, published, expected):
    client = ControlMQTT(repo)
    calls = []
    info = SimpleNamespace(rc=rc, wait_for_publish=lambda **_: calls.append("wait"),
                           is_published=lambda: published)
    client.client = SimpleNamespace(is_connected=lambda: connected,
                                     publish=lambda *args, **kwargs: calls.append("publish") or info)
    command = repo.create_command("D1", "restart_device", "high", DIA)
    assert client.send_command("D1", command) == expected
    assert ("publish" in calls) is connected
    assert ("wait" in calls) is (connected and rc == 0)
