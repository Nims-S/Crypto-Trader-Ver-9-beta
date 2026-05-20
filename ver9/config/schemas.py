from __future__ import annotations

import msgspec


class ExchangeConfig(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    api_key: str
    secret_key: str
    rate_limit_ms: int
    sandbox: bool


class PersistenceConfig(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    log_rotation_bytes: int
    snapshot_interval_seconds: int
    base_dir: str


class RiskConfig(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    max_drawdown: float
    max_position_size: float
    blocked_assets: tuple[str, ...]


class AppConfig(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    environment: str
    debug: bool
    exchange: ExchangeConfig
    persistence: PersistenceConfig
    risk: RiskConfig
