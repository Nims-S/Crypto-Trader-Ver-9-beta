from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExchangeConfig:
    name: str
    api_key: str
    secret_key: str
    rest_url: str
    websocket_url: str
    testnet: bool = False