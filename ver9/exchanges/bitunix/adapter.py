from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from time import time_ns
from uuid import uuid4

import aiohttp

from ver9.events_execution_events import OrderAccepted
from ver9.events_execution_events import OrderRejected
from ver9.events_execution_events import OrderSubmitted
from ver9.events_execution_models import ExchangeExecutionResult
from ver9.events_execution_models import ExchangeFillUpdate
from ver9.events_execution_models import ExchangeOrderUpdate
from ver9.exchanges.base.adapter import BaseExchangeAdapter


class BitunixExchangeAdapter(BaseExchangeAdapter):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._http_session: aiohttp.ClientSession | None = None
        self._websocket: aiohttp.ClientWebSocketResponse | None = None
        self._heartbeat_task: asyncio.Task | None = None

    async def connect(self) -> None:
        self._http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))

        self._websocket = await self._http_session.ws_connect(
            self._config.websocket_url,
            heartbeat=15,
            autoping=True,
        )

        timestamp = str(int(time_ns() / 1_000_000))
        signature_seed = f"{self._config.api_key}{timestamp}"

        signature = hmac.new(
            self._config.secret_key.encode(),
            signature_seed.encode(),
            hashlib.sha256,
        ).hexdigest()

        auth_payload = {
            "op": "login",
            "args": {
                "apiKey": self._config.api_key,
                "timestamp": timestamp,
                "sign": signature,
            },
        }

        await self._websocket.send_json(auth_payload)

        await self._websocket.send_json(
            {
                "op": "subscribe",
                "args": ["order", "execution"],
            }
        )

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()

        if self._websocket is not None:
            await self._websocket.close()

        if self._http_session is not None:
            await self._http_session.close()

    async def submit_order(self, event: OrderSubmitted) -> ExchangeExecutionResult:
        if self._http_session is None:
            raise RuntimeError("bitunix_http_session_not_initialized")

        timestamp = str(int(time_ns() / 1_000_000))

        payload = {
            "symbol": event.symbol,
            "side": event.side.upper(),
            "type": event.order_type.upper(),
            "qty": str(event.quantity),
            "clientOrderId": event.order_id,
        }

        if event.price is not None:
            payload["price"] = str(event.price)

        body = json.dumps(payload, separators=(",", ":"))

        signature_seed = (
            f"{timestamp}{self._config.api_key}{body}"
        )

        signature = hashlib.md5(
            hmac.new(
                self._config.secret_key.encode(),
                signature_seed.encode(),
                hashlib.sha256,
            ).hexdigest().encode()
        ).hexdigest()

        headers = {
            "api-key": self._config.api_key,
            "sign": signature,
            "timestamp": timestamp,
            "Content-Type": "application/json",
        }

        endpoint = f"{self._config.rest_url}/api/v1/order"

        try:

            async def request():
                assert self._http_session is not None

                async with self._http_session.post(
                    endpoint,
                    headers=headers,
                    data=body,
                ) as response:
                    response.raise_for_status()
                    return await response.json()

            response_payload = await self.throttled_request(request())

        except Exception as exc:
            await self._event_bus.publish(
                OrderRejected(
                    event_id=str(uuid4()),
                    timestamp_ns=time_ns(),
                    correlation_id=event.correlation_id,
                    order_id=event.order_id,
                    reason=str(exc),
                )
            )
            raise

        data = response_payload["data"]
        exchange_order_id = str(data["orderId"])

        await self._event_bus.publish(
            OrderAccepted(
                event_id=str(uuid4()),
                timestamp_ns=time_ns(),
                correlation_id=event.correlation_id,
                order_id=event.order_id,
                exchange_order_id=exchange_order_id,
            )
        )

        return ExchangeExecutionResult(
            exchange_order_id=exchange_order_id,
            internal_order_id=event.order_id,
            accepted_price=float(event.price or 0.0),
            timestamp_ns=time_ns(),
            status="NEW",
            position_side="BOTH",
            reduce_only=False,
            is_liquidation=False,
        )

    async def execution_stream(self) -> AsyncIterator[ExchangeOrderUpdate | ExchangeFillUpdate]:
        if self._websocket is None:
            raise RuntimeError("bitunix_websocket_not_initialized")

        async for message in self._websocket:
            try:
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue

                payload = json.loads(message.data)
                topic = str(payload.get("topic", ""))
                data = payload.get("data")

                if not isinstance(data, dict):
                    continue

                if topic == "order":
                    yield ExchangeOrderUpdate(
                        exchange_order_id=str(data.get("orderId", "")),
                        internal_order_id=str(data.get("clientOrderId", "")),
                        status=str(data.get("status", "")),
                        cumulative_filled_quantity=float(data.get("filledQty", 0.0)),
                        remaining_quantity=float(data.get("remainQty", 0.0)),
                        avg_price=float(data.get("avgPrice", 0.0)),
                        reject_reason=None,
                        position_side="BOTH",
                        reduce_only=bool(data.get("reduceOnly", False)),
                        is_liquidation=False,
                    )

                if topic == "execution":
                    yield ExchangeFillUpdate(
                        exchange_order_id=str(data.get("orderId", "")),
                        trade_id=str(data.get("tradeId", "")),
                        fill_price=float(data.get("price", 0.0)),
                        fill_quantity=float(data.get("qty", 0.0)),
                        fill_fee=float(data.get("fee", 0.0)),
                        fee_asset=str(data.get("feeAsset", "USDT")),
                        liquidity_side=str(data.get("liquiditySide", "TAKER")),
                        position_side="BOTH",
                        reduce_only=bool(data.get("reduceOnly", False)),
                        is_liquidation=False,
                    )

            except Exception as exc:
                await self._logger.error(
                    "bitunix_execution_stream_failure",
                    exchange=self.exchange_name,
                    error_type=type(exc).__name__,
                )

    async def _heartbeat_loop(self) -> None:
        if self._websocket is None:
            return

        while self._connected:
            try:
                await self._websocket.send_json({"op": "ping"})
                await asyncio.sleep(10)
            except Exception:
                return
