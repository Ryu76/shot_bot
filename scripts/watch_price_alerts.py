"""Print Discord-ready alerts for configured price triggers; no broker/order code."""
from __future__ import annotations
import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
import yfinance as yf
from shot_bot.alerts import evaluate_price_alerts

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "price_alerts.json"
STATE = ROOT / "data" / "alert_state.json"

def market_is_open(now: datetime) -> bool:
    local = now.astimezone(ZoneInfo("America/New_York"))
    return local.weekday() < 5 and time(9, 30) <= local.time() <= time(16, 0)

def main() -> None:
    if not CONFIG.exists():
        return
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    watchlist = [x for x in config.get("positions", []) if float(x.get("entry_price", 0)) > 0 or float(x.get("stop_price", 0)) > 0]
    if not watchlist or not market_is_open(datetime.now(ZoneInfo("UTC"))):
        return
    prices = {}
    for item in watchlist:
        ticker = item["ticker"].upper()
        try:
            value = yf.Ticker(ticker).fast_info.get("last_price")
            if value: prices[ticker] = float(value)
        except Exception:
            continue
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    alerts, state = evaluate_price_alerts(watchlist, prices, state)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    for alert in alerts:
        label = "🔴 손절 경고" if alert["kind"] == "stop" else "🟡 진입가 도달"
        print(f"{label} | {alert['ticker']} | 현재 ${alert['price']:.2f} | 기준 ${alert['threshold']:.2f}\n직접 주문 여부를 확인하세요. 본 감시기는 주문을 전송하지 않습니다.")
if __name__ == "__main__":
    main()
