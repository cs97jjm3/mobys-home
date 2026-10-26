"""Tests for reading Alexa's replies. No Amazon account or internet needed."""

import alexa_link as al


def endpoint(eid, name, kind):
    return {"endpointId": eid, "friendlyNameObject": {"value": {"text": name}},
            "manufacturer": {"value": {"text": "Tuya"}},
            "displayCategories": {"primary": {"value": kind}}}


def test_reads_power_brightness_and_reachability():
    state = al.read_features({"features": [
        {"name": "power", "operations": [{"name": "turnOn"}, {"name": "turnOff"}],
         "properties": [{"powerStateValue": "ON", "timeOfLastChange": "2026-10-25T10:00:00Z"}]},
        {"name": "brightness", "operations": [{"name": "setBrightness"}],
         "properties": [{"brightnessStateValue": 60}]},
        {"name": "connectivity", "properties": [{"reachabilityStatusValue": "UNREACHABLE"}]},
    ]})
    assert state["power"] == "ON" and state["can_switch"] and state["can_dim"]
    assert state["brightness"] == 60 and state["reachable"] is False
    assert state["power_changed"] > 0


def test_reads_motion_and_light_level():
    state = al.read_features({"features": [
        {"name": "motionSensor", "properties": [{"detectionStateValue": "DETECTED"}]},
        {"name": "lightSensor", "properties": [{"illuminanceValue": {"value": 27.0}}]},
    ]})
    assert state["motion"] == "DETECTED" and state["lux"] == 27.0


def test_skips_properties_with_errors():
    state = al.read_features({"features": [
        {"name": "power", "properties": [{"powerStateValue": "ON", "error": {"type": "X"}}]}]})
    assert "power" not in state


def test_spots_a_refused_change():
    ok = {"data": {"setEndpointFeatures": {"featureControlResponses": [{"code": "SUCCESS"}],
                                           "errors": []}}}
    refused = {"data": {"setEndpointFeatures": {"featureControlResponses": [],
                                                "errors": [{"code": "ENDPOINT_UNREACHABLE"}]}}}
    assert al.control_error(ok) is None
    assert al.control_error(refused) == "ENDPOINT_UNREACHABLE"
    assert al.control_error({}) == "Alexa didn't confirm the change"


def test_snapshot_groups_and_hides():
    alexa = al.Alexa("x", ".")
    alexa.endpoints = [endpoint("1", "Fish tank", "LIGHT"), endpoint("2", "Old lamp", "LIGHT"),
                       endpoint("3", "Front Door", "CAMERA"), endpoint("4", "Printer", "PRINTER")]
    alexa.states = {"1": {"power": "ON", "can_switch": True}, "3": {"motion": "NOT_DETECTED"}}
    alexa.routines = ["Alexa, goodnight", "Old routine"]
    snap = alexa.snapshot(hidden=["old lamp", "Old routine"])
    assert [s["name"] for s in snap["switches"]] == ["Fish tank"]
    assert snap["switches"][0]["label"] == "Light"
    assert [s["name"] for s in snap["sensors"]] == ["Front Door"]
    assert [s["name"] for s in snap["other"]] == ["Printer"]
    assert snap["routines"] == ["Alexa, goodnight"]


def test_colour_light_features():
    import alexa_link as al
    features = {"features": [
        {"name": "power", "operations": [{"name": "turnOn"}, {"name": "turnOff"}],
         "properties": [{"powerStateValue": "ON"}]},
        {"name": "color", "operations": [{"name": "setColor"}],
         "properties": [{"__typename": "Color", "colorStateValue": {"hue": 120.0, "saturation": 1.0, "brightness": 1.0}}]},
        {"name": "colorTemperature", "operations": [{"name": "setColorTemperature"}],
         "properties": [{"__typename": "ColorTemperature", "name": "colorTemperatureInKelvin"}]},
    ]}
    out = al.read_features(features)
    assert out["can_colour"] and out["can_white"] and out["hue"] == 120


def test_white_light_has_no_hue():
    import alexa_link as al
    features = {"features": [{"name": "color", "operations": [{"name": "setColor"}],
                              "properties": [{"colorStateValue": {"hue": 0.0, "saturation": 0.0, "brightness": 0.0}}]}]}
    out = al.read_features(features)
    assert out["can_colour"] and "hue" not in out


def test_set_colour_sends_what_alexa_accepted():
    import asyncio, alexa_link as al
    a = al.Alexa.__new__(al.Alexa)
    a.states = {"x": {"brightness": 50}}
    sent = []

    async def fake(eid, feature, op, payload=None):
        sent.append((feature, op, payload))
    a._control = fake
    asyncio.run(a.set_colour("x", 120))
    asyncio.run(a.set_white("x", 2700))
    assert sent[0] == ("color", "setColor", {"color": {"hue": 120.0, "saturation": 1.0, "brightness": 0.5}})
    assert sent[1] == ("colorTemperature", "setColorTemperature", {"colorTemperatureInKelvin": 2700})
