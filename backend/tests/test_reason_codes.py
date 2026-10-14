"""MQTT reason-code helper behavior (C-W02-03).

Regression guard: paho-mqtt 2.x delivers MQTT v5 outcomes as
``ReasonCode`` objects whose ``is_failure`` is a boolean *property*,
while the v3 path delivers plain integers. Treating the property as a
method (or feeding the object to ``int()``) raises inside the network
callback and silently breaks CONNECT handling — this test pins the
helper against the real installed client library.
"""

from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from coldguard_backend.mqtt_consumer import reason_failed


def test_v5_success_reason_is_not_failure():
    assert reason_failed(ReasonCode(PacketTypes.CONNACK, "Success")) is False


def test_v5_refused_reason_is_failure():
    assert reason_failed(ReasonCode(PacketTypes.CONNACK, "Not authorized")) is True


def test_integer_return_codes():
    assert reason_failed(0) is False
    assert reason_failed(5) is True


def test_none_is_not_failure():
    assert reason_failed(None) is False
