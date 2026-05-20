from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from time import time_ns
from uuid import uuid4

import aiohttp

from ver9.events.execution_events import OrderAccepted
from ver9.events.execution_events import OrderRejected
from ver9.events.execution_events import OrderSubmitted
from ver9.events.execution_models import ExchangeExecutionResult
from ver9.events.execution_models import ExchangeFillUpdate
from ver9.events.execution_models import ExchangeOrderUpdate
from ver9.exchanges.base.adapter import BaseExchangeAdapter


class BybitExchangeAdapter(BaseExchangeAdapter):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._http_session: aiohttp.ClientSession | None = None
        self._websocket: aiohttp.ClientWebSocketResponse | None = None

    async def connect(self) -> None:
        self._http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        self._websocket = await self._http_session.ws_connect(self._config.websocket_url, heartbeat=20, autoping=True)

        expires = str(int(time_ns() / 1_000_000) + 5000)
        payload = f"GET/realtime{expires}"
        signature = hmac.new(self._config.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()

        await self._websocket.send_json({
            "op": "auth",
            "args": [self._config.api_key, expires, signature],
        })

        await self._websocket.send_json({
            "op": "subscribe",
            "args": ["execution"],
        })

        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False
        if self._websocket is not None:
            await self._websocket.close()
        if self._http_session is not None:
            await self._http_session.close()

    async def submit_order(self, event: OrderSubmitted) -> ExchangeExecutionResult:
        if self._http_session is None:
            raise RuntimeError("bybit_http_session_not_initialized")

        timestamp = str(int(time_ns() / 1_000_000))
        recv_window = "5000"

        body = {
            "category": "linear",
            "symbol": event.symbol,
            "side": event.side.capitalize(),
            "orderType": event.order_type.capitalize(),
            "qty": str(event.quantity),
            "orderLinkId": event.order_id,
        }

        if event.price is not None:
            body["price"] = str(event.price)

        body_json = json.dumps(body, separators=(",", ":"))
        raw = f"{timestamp}{self._config.api_key}{recv_window}{body_json}"
        signature = hmac.new(self._config.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()

        headers = {
            "X-BAPI-API-KEY": self._config.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json",
        }

        endpoint = f"{self._config.rest_url}/v5/order/create"

        try:
            async def request():
                assert self._http_session is not None
                async with self._http_session.post(endpoint, headers=headers, data=body_json) as response:
                    response.raise_for_status()
                    return await response.json()

            response_payload = await self.throttled_request(request())

        except Exception as exc:
            await self._event_bus.publish(OrderRejected(event_id=str(uuid4()), timestamp_ns=time_ns(), correlation_id=event.correlation_id, order_id=event.order_id, reason=str(exc)))
            raise

        result = response_payload["result"]
        exchange_order_id = str(result["orderId"])

        await self._event_bus.publish(OrderAccepted(event_id=str(uuid4()), timestamp_ns=time_ns(), correlation_id=event.correlation_id, order_id=event.order_id, exchange_order_id=exchange_order_id))

        return ExchangeExecutionResult(exchange_order_id=exchange_order_id, internal_order_id=event.order_id, accepted_price=float(event.price or 0.0), timestamp_ns=time_ns(), status="NEW")

    async def execution_stream(self) -> AsyncIterator[ExchangeOrderUpdate | ExchangeFillUpdate]:
        if self._websocket is None:
            raise RuntimeError("bybit_websocket_not_initialized")

        async for message in self._websocket:
            try:
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue

                payload = json.loads(message.data)

                if payload.get("topic") != "execution":
                    continue

                for execution in payload.get("data", []):
                    yield ExchangeOrderUpdate(
                        exchange_order_id=str(execution.get("orderId", "")),
                        internal_order_id=str(execution.get("orderLinkId", "")),
                        status=str(execution.get("orderStatus", "")),
                        cumulative_filled_quantity=float(execution.get("cumExecQty", 0.0)),
                        remaining_quantity=float(execution.get("leavesQty", 0.0)),
                        avg_price=float(execution.get("avgPrice", 0.0)),
                        reject_reason=None,
                        position_side="BOTH",
                        reduce_only=bool(execution.get("reduceOnly", False)),
                        is_liquidation=False,
                    )

                    if float(execution.get("execQty", 0.0)) > 0:
                        yield ExchangeFillUpdate(
                            exchange_order_id=str(execution.get("orderId", "")),
                            trade_id=str(execution.get("execId", "")),
                            fill_price=float(execution.get("execPrice", 0.0)),
                            fill_quantity=float(execution.get("execQty", 0.0)),
                            fill_fee=float(execution.get("execFee", 0.0)),
                            fee_asset=str(execution.get("feeCurrency", "USDT")),
                            liquidity_side=str(execution.get("execType", "TAKER")),
                            position_side="BOTH",
                            reduce_only=bool(execution.get("reduceOnly", False)),
                            is_liquidation=False,
                        )
            except Exception as exc:
                await self._logger.error("bybit_execution_stream_failure", exchange=self.exchange_name, error_type=type(exc).__name__)
