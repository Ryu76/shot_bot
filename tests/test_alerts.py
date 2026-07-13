from shot_bot.alerts import evaluate_price_alerts


def test_entry_and_stop_alerts_fire_once_then_rearm():
    watch = [{"ticker": "AAA", "entry_price": 100, "entry_direction": "at_or_below", "stop_price": 93}]
    state = {}

    first, state = evaluate_price_alerts(watch, {"AAA": 99}, state)
    repeated, state = evaluate_price_alerts(watch, {"AAA": 98}, state)
    _, state = evaluate_price_alerts(watch, {"AAA": 102}, state)
    rearmed, state = evaluate_price_alerts(watch, {"AAA": 99}, state)
    stopped, _ = evaluate_price_alerts(watch, {"AAA": 92}, state)

    assert [item["kind"] for item in first] == ["entry"]
    assert repeated == []
    assert [item["kind"] for item in rearmed] == ["entry"]
    assert [item["kind"] for item in stopped] == ["stop"]
