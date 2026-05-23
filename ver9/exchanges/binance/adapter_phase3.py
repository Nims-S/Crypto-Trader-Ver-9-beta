"""Phase 3: Binance Exchange Adapter - Domain Event Emitter.

Key changes:
1. Inherits from BaseExchangeAdapterPhase3
2. Accepts OrderSubmittedDomain (canonical)
3. Publishes ONLY domain events via EventPublisher
4. NO direct imports of ver9.runtime or legacy event types
5. Uses AsyncLogger and MetricsCollector protocols
"""
from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from time import time_ns
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import aiohttp

from ver9.domain.events.execution import (
    OrderSubmittedDomain,
    OrderAcceptedDomain,
    OrderRejectedDomain,
    FillReceivedDomain,
)
from ver9.events.execution_models import (
    ExchangeExecutionResult,
    ExchangeOrderUpdate,
    ExchangeFillUpdate,
)
from ver9.exchanges.base.adapter_phase3 import BaseExchangeAdapterPhase3


class BinanceExchangeAdapterPhase3(BaseExchangeAdapterPhase3):
    """Binance Spot/Futures execution adapter - canonical domain events."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._http_session: aiohttp.ClientSession | None = None
        self._websocket: aiohttp.ClientWebSocketResponse | None = None
        self._listen_key: str | None = None

    async def connect(self) -> None:
        """Connect to Binance websocket."""
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        self._listen_key = await self._create_listen_key()
        websocket_url = f"{self._config.websocket_url}/{self._listen_key}"
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
        """Disconnect from Binance."""
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
        event: OrderSubmittedDomain,
    ) -> ExchangeExecutionResult:
        """Submit order to Binance via REST.
        
        Accepts canonical OrderSubmittedDomain, emits domain events.
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
            "newClientOrderId": event.internal_order_id,
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

        headers = {"X-MBX-APIKEY": self._config.api_key}
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

            response_payload = await self.throttled_request(request())
        except Exception as exc:
            await self._logger.error(
                "binance_order_submission_failed",
                exchange=self.exchange_name,
                internal_order_id=event.internal_order_id,
                error_type=type(exc).__name__,
            )
            rejection = OrderRejectedDomain(
                internal_order_id=event.internal_order_id,
                exchange=self.exchange_name,
                reason=str(exc),
                timestamp=time_ns(),
            )
            await self._event_publisher.publish_order_rejected(rejection)
            raise

        exchange_order_id = str(response_payload["orderId"])
        
        # Publish OrderAcceptedDomain event
        acceptance = OrderAcceptedDomain(
            internal_order_id=event.internal_order_id,
            exchange_order_id=exchange_order_id,
            exchange=self.exchange_name,
            timestamp=time_ns(),
        )
        await self._event_publisher.publish_order_accepted(acceptance)

        self._metrics.increment_counter(
            "binance_orders_submitted",
            {"exchange": self.exchange_name},
        )

        accepted_price = (
            float(response_payload.get("price", 0.0))
            if response_payload.get("price") is not None
            else 0.0
        )

        return ExchangeExecutionResult(
            exchange_order_id=exchange_order_id,
            internal_order_id=event.internal_order_id,
            accepted_price=accepted_price,
            timestamp_ns=time_ns(),
            status=str(response_payload.get("status", "NEW")),
        )

    async def execution_stream(
        self,
    ) -> AsyncIterator[ExchangeOrderUpdate | ExchangeFillUpdate]:
        """Stream normalized execution updates from Binance."""
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
                cumulative_filled_quantity = float(payload.get("z", 0.0))
                original_quantity = float(payload.get("q", 0.0))
                remaining_quantity = max(
                    original_quantity - cumulative_filled_quantity, 0.0
                )
                avg_price = float(payload.get("L", 0.0))

                if execution_type in {
                    "NEW", "CANCELED", "REPLACED", "REJECTED", "EXPIRED"
                }:
                    yield ExchangeOrderUpdate(
                        exchange_order_id=str(payload.get("i", "")),
                        internal_order_id=str(payload.get("c", "")),
                        status=str(payload.get("X", "")),
                        cumulative_filled_quantity=cumulative_filled_quantity,
                        remaining_quantity=remaining_quantity,
                        avg_price=avg_price,
                        reject_reason=(
                            str(payload.get("r"))
                            if payload.get("r") not in {None, "NONE"}
                            else None
                        ),
                    )

                if execution_type in {"TRADE", "PARTIALLY_FILLED"}:
                    yield ExchangeFillUpdate(
                        exchange_order_id=str(payload.get("i", "")),
                        trade_id=str(payload.get("t", "")),
                        fill_price=float(payload.get("L", 0.0)),
                        fill_quantity=float(payload.get("l", 0.0)),
                        fill_fee=float(payload.get("n", 0.0)),
                        fee_asset=str(payload.get("N", "")),
                        liquidity_side=(
                            "MAKER"
                            if bool(payload.get("m", False))
                            else "TAKER"
                        ),
                    )
            except Exception as exc:
                await self._logger.error(
                    "binance_execution_stream_parse_failure",
                    exchange=self.exchange_name,
                    correlation_id=self._extract_correlation_id(payload),
                    error_type=type(exc).__name__,
                )

    async def _create_listen_key(self) -> str:
        """Create Binance userdata stream listen key."""
        if self._http_session is None:
            raise RuntimeError("binance_http_session_not_initialized")
        
        endpoint = f"{self._config.rest_url}/api/v3/userDataStream"
        headers = {"X-MBX-APIKEY": self._config.api_key}

        async def request() -> dict[str, Any]:
            assert self._http_session is not None
            async with self._http_session.post(
                endpoint,
                headers=headers,
            ) as response:
                response.raise_for_status()
                return await response.json()

        response_payload = await self.throttled_request(request())
        listen_key = response_payload.get("listenKey")
        if not isinstance(listen_key, str):
            raise RuntimeError("invalid_binance_listen_key")
        return listen_key

    async def _check_connection_health(self) -> bool:
        """Check websocket health."""
        return (
            self._websocket is not None
            and not self._websocket.closed
        )

    @staticmethod
    def _format_float(value: float) -> str:
        return format(value, ".8f").rstrip("0").rstrip(".")

    @staticmethod
    def _extract_correlation_id(payload: dict[str, Any]) -> str:
        client_order_id = payload.get("c")
        return str(client_order_id) if client_order_id else "unknown"
