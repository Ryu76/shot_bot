"""한국투자증권 해외주식 OpenAPI 클라이언트.

각 메서드의 키워드 인자는 ``hantoo_api`` 폴더의 Excel 명세에 있는
Request Query 또는 Request Body의 Element 이름을 그대로 사용한다.
GET 메서드는 쿼리스트링으로, POST 메서드는 JSON 본문으로 전달된다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Literal
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LIVE_BASE_URL = "https://openapi.koreainvestment.com:9443"
PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"


def load_dotenv(path: str | Path = ".env", *, override: bool = False) -> None:
    """Load simple ``KEY=value`` pairs without adding a dotenv dependency.

    Existing environment variables win unless ``override=True`` is requested.
    The file is deliberately optional, so deployment platforms can inject the
    same values as real environment variables instead.
    """
    dotenv_path = Path(path)
    if not dotenv_path.is_file():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key:
            raise ValueError(f"invalid .env entry: {raw_line!r}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"missing required environment variable: {name}")
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"{name} must be true or false")


class HantooAPIError(RuntimeError):
    """HTTP 요청 또는 한국투자 OpenAPI가 반환한 오류."""


@dataclass(frozen=True)
class Endpoint:
    method: Literal["GET", "POST"]
    path: str
    tr_id: str | None
    name: str


def _endpoint(method: Literal["GET", "POST"], path: str, tr_id: str | None, name: str):
    """Attach the documented endpoint metadata to a client method."""

    endpoint = Endpoint(method, path, tr_id, name)

    def decorate(function):
        function.endpoint = endpoint
        return function

    return decorate


class HantooClient:
    """해외주식 REST API 호출기.

    Parameters are never persisted or logged. ``paper=True`` selects the
    모의투자 domain; endpoints not supported by 모의투자는 live domain을
    사용해야 한다.
    """

    def __init__(self, app_key: str, app_secret: str, access_token: str, *, paper: bool = False, timeout: float = 10.0):
        if not all((app_key, app_secret, access_token)):
            raise ValueError("app_key, app_secret, and access_token are required")
        self.app_key = app_key
        self.app_secret = app_secret
        self.access_token = access_token.removeprefix("Bearer ").strip()
        self.paper = paper
        self.base_url = PAPER_BASE_URL if paper else LIVE_BASE_URL
        self.timeout = timeout

    @classmethod
    def from_env(cls, *, dotenv_path: str | Path = ".env", timeout: float = 10.0) -> "HantooClient":
        """Create a client from ``.env`` or process environment variables.

        Required keys are ``HANTOO_APP_KEY``, ``HANTOO_APP_SECRET``, and
        ``HANTOO_ACCESS_TOKEN``. Set ``HANTOO_PAPER=true`` for 모의투자.
        """
        load_dotenv(dotenv_path)
        return cls(
            _required_env("HANTOO_APP_KEY"),
            _required_env("HANTOO_APP_SECRET"),
            _required_env("HANTOO_ACCESS_TOKEN"),
            paper=_env_bool("HANTOO_PAPER", default=True),
            timeout=timeout,
        )

    def _invoke(self, endpoint: Endpoint, values: dict[str, Any]) -> dict[str, Any]:
        """Call an endpoint. ``tr_id`` overrides the documented default when needed."""
        values = {key: value for key, value in values.items() if value is not None}
        tr_id = values.pop("tr_id", endpoint.tr_id)
        if not tr_id:
            raise ValueError(f"{endpoint.name} requires tr_id; select it from the API specification")
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }
        url = f"{self.base_url}{endpoint.path}"
        body: bytes | None = None
        if endpoint.method == "GET":
            if values:
                url += "?" + urlencode(values, doseq=True)
        else:
            body = json.dumps(values, ensure_ascii=False).encode("utf-8")
        request = Request(url, data=body, headers=headers, method=endpoint.method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise HantooAPIError(f"{endpoint.name} failed ({error.code}): {detail}") from error
        except OSError as error:
            raise HantooAPIError(f"{endpoint.name} request failed: {error}") from error
        if payload.get("rt_cd") not in (None, "0"):
            raise HantooAPIError(f"{endpoint.name} failed: {payload.get('msg1', payload)}")
        return payload

    # 기본시세
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/price-detail", "HHDFS76200200", "해외주식 현재가상세")
    def price_detail(self, **params: Any) -> dict[str, Any]: return self._invoke(self.price_detail.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/inquire-asking-price", "HHDFS76200100", "해외주식 현재가 호가")
    def asking_price(self, **params: Any) -> dict[str, Any]: return self._invoke(self.asking_price.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/price", "HHDFS00000300", "해외주식 현재체결가")
    def price(self, **params: Any) -> dict[str, Any]: return self._invoke(self.price.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/inquire-ccnl", "HHDFS76200300", "해외주식 체결추이")
    def executions(self, **params: Any) -> dict[str, Any]: return self._invoke(self.executions.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice", "HHDFS76950200", "해외주식분봉조회")
    def stock_minute_chart(self, **params: Any) -> dict[str, Any]: return self._invoke(self.stock_minute_chart.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/inquire-time-indexchartprice", "FHKST03030200", "해외지수분봉조회")
    def index_minute_chart(self, **params: Any) -> dict[str, Any]: return self._invoke(self.index_minute_chart.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/dailyprice", "HHDFS76240000", "해외주식 기간별시세")
    def stock_daily_prices(self, **params: Any) -> dict[str, Any]: return self._invoke(self.stock_daily_prices.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice", "FHKST03030100", "해외주식 종목/지수/환율 기간별시세")
    def daily_chart_prices(self, **params: Any) -> dict[str, Any]: return self._invoke(self.daily_chart_prices.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/inquire-search", "HHDFS76410000", "해외주식 조건검색")
    def stock_search(self, **params: Any) -> dict[str, Any]: return self._invoke(self.stock_search.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/quotations/countries-holiday", "CTOS5011R", "해외결제일자조회")
    def countries_holiday(self, **params: Any) -> dict[str, Any]: return self._invoke(self.countries_holiday.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/search-info", "CTPF1702R", "해외주식 상품기본정보")
    def stock_info(self, **params: Any) -> dict[str, Any]: return self._invoke(self.stock_info.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/industry-theme", "HHDFS76370000", "해외주식 업종별시세")
    def industry_theme(self, **params: Any) -> dict[str, Any]: return self._invoke(self.industry_theme.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/industry-price", "HHDFS76370100", "해외주식 업종별코드조회")
    def industry_price(self, **params: Any) -> dict[str, Any]: return self._invoke(self.industry_price.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/multprice", "HHDFS76220000", "해외주식 복수종목 시세조회")
    def multiple_prices(self, **params: Any) -> dict[str, Any]: return self._invoke(self.multiple_prices.endpoint, params)

    # 시세분석
    @_endpoint("GET", "/uapi/overseas-stock/v1/ranking/price-fluct", "HHDFS76260000", "해외주식 가격급등락")
    def price_fluctuation(self, **params: Any) -> dict[str, Any]: return self._invoke(self.price_fluctuation.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/ranking/volume-surge", "HHDFS76270000", "해외주식 거래량급증")
    def volume_surge(self, **params: Any) -> dict[str, Any]: return self._invoke(self.volume_surge.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/ranking/volume-power", "HHDFS76280000", "해외주식 매수체결강도상위")
    def volume_power(self, **params: Any) -> dict[str, Any]: return self._invoke(self.volume_power.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/ranking/updown-rate", "HHDFS76290000", "해외주식 상승율/하락율")
    def updown_rate(self, **params: Any) -> dict[str, Any]: return self._invoke(self.updown_rate.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/ranking/new-highlow", "HHDFS76300000", "해외주식 신고/신저가")
    def new_highlow(self, **params: Any) -> dict[str, Any]: return self._invoke(self.new_highlow.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/ranking/trade-vol", "HHDFS76310010", "해외주식 거래량순위")
    def trade_volume_ranking(self, **params: Any) -> dict[str, Any]: return self._invoke(self.trade_volume_ranking.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/ranking/trade-pbmn", "HHDFS76320010", "해외주식 거래대금순위")
    def trade_amount_ranking(self, **params: Any) -> dict[str, Any]: return self._invoke(self.trade_amount_ranking.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/ranking/trade-growth", "HHDFS76330000", "해외주식 거래증가율순위")
    def trade_growth_ranking(self, **params: Any) -> dict[str, Any]: return self._invoke(self.trade_growth_ranking.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/ranking/trade-turnover", "HHDFS76340000", "해외주식 거래회전율순위")
    def trade_turnover_ranking(self, **params: Any) -> dict[str, Any]: return self._invoke(self.trade_turnover_ranking.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/ranking/market-cap", "HHDFS76350100", "해외주식 시가총액순위")
    def market_cap_ranking(self, **params: Any) -> dict[str, Any]: return self._invoke(self.market_cap_ranking.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/period-rights", "CTRGT011R", "해외주식 기간별권리조회")
    def period_rights(self, **params: Any) -> dict[str, Any]: return self._invoke(self.period_rights.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/news-title", "HHPSTH60100C1", "해외뉴스종합")
    def news_titles(self, **params: Any) -> dict[str, Any]: return self._invoke(self.news_titles.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/rights-by-ice", "HHDFS78330900", "해외주식 권리종합")
    def rights_by_ice(self, **params: Any) -> dict[str, Any]: return self._invoke(self.rights_by_ice.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/colable-by-company", "CTLN4050R", "해외주식담보대출 가능 종목")
    def collateral_available(self, **params: Any) -> dict[str, Any]: return self._invoke(self.collateral_available.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-price/v1/quotations/brknews-title", "FHKST01011801", "해외속보")
    def breaking_news_titles(self, **params: Any) -> dict[str, Any]: return self._invoke(self.breaking_news_titles.endpoint, params)

    # 주문/계좌 -- 국가와 매수/매도에 맞는 TR ID를 ``tr_id=``로 지정한다.
    @_endpoint("POST", "/uapi/overseas-stock/v1/trading/order", None, "해외주식 주문")
    def order(self, **body: Any) -> dict[str, Any]: return self._invoke(self.order.endpoint, body)
    @_endpoint("POST", "/uapi/overseas-stock/v1/trading/order-rvsecncl", None, "해외주식 정정취소주문")
    def revise_cancel_order(self, **body: Any) -> dict[str, Any]: return self._invoke(self.revise_cancel_order.endpoint, body)
    @_endpoint("POST", "/uapi/overseas-stock/v1/trading/order-resv", None, "해외주식 예약주문접수")
    def reserve_order(self, **body: Any) -> dict[str, Any]: return self._invoke(self.reserve_order.endpoint, body)
    @_endpoint("POST", "/uapi/overseas-stock/v1/trading/order-resv-ccnl", "TTTT3017U", "해외주식 예약주문접수취소")
    def cancel_reserve_order(self, **body: Any) -> dict[str, Any]: return self._invoke(self.cancel_reserve_order.endpoint, body)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/inquire-psamount", "TTTS3007R", "해외주식 매수가능금액조회")
    def purchase_amount(self, **params: Any) -> dict[str, Any]: return self._invoke(self.purchase_amount.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/inquire-nccs", "TTTS3018R", "해외주식 미체결내역")
    def unfilled_orders(self, **params: Any) -> dict[str, Any]: return self._invoke(self.unfilled_orders.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/inquire-balance", "TTTS3012R", "해외주식 잔고")
    def balance(self, **params: Any) -> dict[str, Any]: return self._invoke(self.balance.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/inquire-ccnl", "TTTS3035R", "해외주식 주문체결내역")
    def order_executions(self, **params: Any) -> dict[str, Any]: return self._invoke(self.order_executions.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/inquire-present-balance", "CTRP6504R", "해외주식 체결기준현재잔고")
    def present_balance(self, **params: Any) -> dict[str, Any]: return self._invoke(self.present_balance.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/order-resv-list", None, "해외주식 예약주문조회")
    def reserved_orders(self, **params: Any) -> dict[str, Any]: return self._invoke(self.reserved_orders.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/inquire-paymt-stdr-balance", "CTRP6010R", "해외주식 결제기준잔고")
    def settlement_balance(self, **params: Any) -> dict[str, Any]: return self._invoke(self.settlement_balance.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/inquire-period-trans", "CTOS4001R", "해외주식 일별거래내역")
    def period_transactions(self, **params: Any) -> dict[str, Any]: return self._invoke(self.period_transactions.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/inquire-period-profit", "TTTS3039R", "해외주식 기간손익")
    def period_profit(self, **params: Any) -> dict[str, Any]: return self._invoke(self.period_profit.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/foreign-margin", "TTTC2101R", "해외증거금 통화별조회")
    def foreign_margin(self, **params: Any) -> dict[str, Any]: return self._invoke(self.foreign_margin.endpoint, params)
    @_endpoint("POST", "/uapi/overseas-stock/v1/trading/daytime-order", None, "해외주식 미국주간주문")
    def daytime_order(self, **body: Any) -> dict[str, Any]: return self._invoke(self.daytime_order.endpoint, body)
    @_endpoint("POST", "/uapi/overseas-stock/v1/trading/daytime-order-rvsecncl", "TTTS6038U", "해외주식 미국주간정정취소")
    def daytime_revise_cancel(self, **body: Any) -> dict[str, Any]: return self._invoke(self.daytime_revise_cancel.endpoint, body)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/algo-ordno", "TTTS6058R", "해외주식 지정가주문번호조회")
    def algo_order_number(self, **params: Any) -> dict[str, Any]: return self._invoke(self.algo_order_number.endpoint, params)
    @_endpoint("GET", "/uapi/overseas-stock/v1/trading/inquire-algo-ccnl", "TTTS6059R", "해외주식 지정가체결내역조회")
    def algo_executions(self, **params: Any) -> dict[str, Any]: return self._invoke(self.algo_executions.endpoint, params)


def websocket_subscription(tr_id: str, tr_key: str, *, tr_type: str = "1", approval_key: str | None = None) -> dict[str, dict[str, str]]:
    """실시간시세 WebSocket에 보낼 구독(1)/해제(2) 메시지를 만든다."""
    header = {"tr_type": tr_type, "content-type": "utf-8"}
    if approval_key:
        header["approval_key"] = approval_key
    return {"header": header, "body": {"input": {"tr_id": tr_id, "tr_key": tr_key}}}


def realtime_asking_price(tr_key: str, **kwargs: str) -> dict[str, dict[str, str]]:
    """해외주식 실시간호가(HDFSASP0) 구독 메시지."""
    return websocket_subscription("HDFSASP0", tr_key, **kwargs)


def delayed_asia_asking_price(tr_key: str, **kwargs: str) -> dict[str, dict[str, str]]:
    """해외주식 지연호가(아시아, HDFSASP1) 구독 메시지."""
    return websocket_subscription("HDFSASP1", tr_key, **kwargs)


def delayed_execution_price(tr_key: str, **kwargs: str) -> dict[str, dict[str, str]]:
    """해외주식 실시간지연체결가(HDFSCNT0) 구독 메시지."""
    return websocket_subscription("HDFSCNT0", tr_key, **kwargs)


def execution_notice(tr_key: str, **kwargs: str) -> dict[str, dict[str, str]]:
    """해외주식 실시간체결통보(H0GSCNI0) 구독 메시지."""
    return websocket_subscription("H0GSCNI0", tr_key, **kwargs)
