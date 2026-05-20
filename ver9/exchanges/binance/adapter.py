from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from time import time_ns
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import aiohttp

from ver9.events.execution_events import FillReceived
from ver9.events.execution_events import OrderAccepted
from ver9.events.execution_events import OrderRejected
from ver9.events.execution_events import OrderSubmitted
from ver9.exchanges.base.adapter import BaseExchangeAdapter


class ExchangeExecutionResult:
    def __init__(
        self,
        *,
        exchange_order_id: str,
        status: str,
    ) -> None:
        self.exchange_order_id = exchange_order_id
        self.status = status


class ExchangeOrderUpdate:
    def __init__(
        self,
        *,
        order_id: str,
        exchange_order_id: str,
        status: str,
    ) -> None:
        self.order_id = order_id
        self.exchange_order_id = exchange_order_id
        self.status = status


class ExchangeFillUpdate:
    def __init__(
        self,
        *,
        order_id: str,
        fill_id: str,
        price: float,
        quantity: float,
        fee: float,
        fee_asset: str,
    ) -> None:
        self.order_id = order_id
        self.fill_id = fill_id
        self.price = price
        self.quantity = quantity
        self.fee = fee
        self.fee_asset = fee_asset


class BinanceExchangeAdapter(BaseExchangeAdapter):
    """
    Production Binance Spot/Futures execution adapter.

    Responsibilities:
    - signed REST execution
    - websocket lifecycle management
    - execution report normalization
    - resilient exchange connectivity

    Non-Responsibilities:
    - balance mutation
    - position ownership
    - runtime state management
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._http_session: aiohttp.ClientSession | None = None
        self._websocket: aiohttp.ClientWebSocketResponse | None = None
        self._listen_key: str | None = None

    async def connect(self) -> None:
        """
        Establish authenticated Binance websocket session.
        """

        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )

        self._listen_key = await self._create_listen_key()

        websocket_url = (
            f"{self._config.websocket_url}/{self._listen_key}"
        )

        self._websocket = await self._http_session.ws_connect(
            websocket_url,
            heartbeat=30,
            autoping=True,
        )

        self._connected = True

        await self._logger.info(
            "binance_websocket_connected",
            exchange=self.exchange_name,
        )

    async def disconnect(self) -> None:
        """
        Gracefully terminate Binance connections.
        """

        self._connected = False

        if self._websocket is not None:
            await self._websocket.close()

        if self._http_session is not None:
            await self._http_session.close()

        await self._logger.info(
            "binance_websocket_disconnected",
            exchange=self.exchange_name,
        )

    async def submit_order(
        self,
        event: OrderSubmitted,
    ) -> ExchangeExecutionResult:
        """
        Submit signed Binance REST execution request.
        """

        if self._http_session is None:
            raise RuntimeError("binance_http_session_not_initialized")

        timestamp = int(time_ns() / 1_000_000)

        payload = {
            "symbol": event.symbol,
            "side": event.side.upper(),
            "type": event.order_type.upper(),
            "quantity": self._format_float(event.quantity),
            "timestamp": str(timestamp),
            "newClientOrderId": event.order_id,
        }

        if event.price is not None:
            payload["price"] = self._format_float(event.price)
            payload["timeInForce"] = "GTC"

        query_string = urlencode(payload)

        signature = hmac.new(
            self._config.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        payload["signature"] = signature

        headers = {
            "X-MBX-APIKEY": self._config.api_key,
        }

        endpoint = f"{self._config.rest_url}/api/v3/order"

        try:

            async def request() -> dict[str, Any]:
                assert self._http_session is not None

                async with self._http_session.post(
                    endpoint,
                    headers=headers,
                    data=payload,
                ) as response:
                    response.raise_for_status()
                    return await response.json()

            response_payload = await self.throttled_request(
                request()
            )

        except Exception as exc:
            await self._logger.error(
                "binance_order_submission_failed",
                exchange=self.exchange_name,
                correlation_id=event.correlation_id,
                error_type=type(exc).__name__,
            )

            await self.event_bus.publish(
                OrderRejected(
                    event_id=str(uuid4()),
                    timestamp_ns=time_ns(),
                    correlation_id=event.correlation_id,
                    order_id=event.order_id,
                    reason=str(exc),
                )
            )

            raise

        exchange_order_id = str(response_payload["orderId"])

        await self.event_bus.publish(
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
            status=str(response_payload.get("status", "NEW")),
        )

    async def execution_stream(
        self,
    ) -> AsyncIterator[
        ExchangeOrderUpdate | ExchangeFillUpdate
    ]:
        """
        Yield normalized Binance execution updates.
        """

        if self._websocket is None:
            raise RuntimeError("binance_websocket_not_initialized")

        async for message in self._websocket:

            payload: dict[str, Any] = {}

            try:
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue

                payload = json.loads(message.data)

                event_type = str(payload.get("e", ""))

                if event_type != "executionReport":
                    continue

                execution_type = str(payload.get("x", ""))

                if execution_type in {"NEW", "CANCELED", "REPLACED"}:
                    yield ExchangeOrderUpdate(
                        order_id=str(payload.get("c", "")),
                        exchange_order_id=str(payload.get("i", "")),
                        status=str(payload.get("X", "")),
                    )

                if execution_type in {"TRADE", "PARTIALLY_FILLED"}:
                    yield ExchangeFillUpdate(
                        order_id=str(payload.get("c", "")),
                        fill_id=str(payload.get("t", "")),
                        price=float(payload.get("L", 0.0)),
                        quantity=float(payload.get("l", 0.0)),
                        fee=float(payload.get("n", 0.0)),
                        fee_asset=str(payload.get("N", "")),
                    )

            except Exception as exc:
                await self._logger.error(
                    "binance_execution_stream_parse_failure",
                    exchange=self.exchange_name,
                    correlation_id=self._extract_correlation_id(payload),
                    error_type=type(exc).__name__,
                )

    async def _create_listen_key(self) -> str:
        """
        Create Binance user stream listen key.
        """

        if self._http_session is None:
            raise RuntimeError("binance_http_session_not_initialized")

        endpoint = (
            f"{self._config.rest_url}/api/v3/userDataStream"
        )

        headers = {
            "X-MBX-APIKEY": self._config.api_key,
        }

        async def request() -> dict[str, Any]:
            assert self._http_session is not None

            async with self._http_session.post(
                endpoint,
                headers=headers,
            ) as response:
                response.raise_for_status()
                return await response.json()

        response_payload = await self.throttled_request(
            request()
        )

        listen_key = response_payload.get("listenKey")

        if not isinstance(listen_key, str):
            raise RuntimeError("invalid_binance_listen_key")

        return listen_key

    async def _check_connection_health(self) -> bool:
        """
        Binance websocket heartbeat validation.
        """

        return (
            self._websocket is not None
            and not self._websocket.closed
        )

    @staticmethod
    def _format_float(value: float) -> str:
        return format(value, ".8f").rstrip("0").rstrip(".")

    @staticmethod
    def _extract_correlation_id(
        payload: dict[str, Any],
    ) -> str:
        client_order_id = payload.get("c")

        if client_order_id is None:
            return "unknown"

        return str(client_order_id)
