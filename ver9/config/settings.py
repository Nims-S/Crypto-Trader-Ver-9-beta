from __future__ import annotations

import asyncio
import os
import tomllib
from pathlib import Path

import msgspec

from .schemas import AppConfig


class ConfigError(RuntimeError):
    pass


class ConfigNotLoadedError(ConfigError):
    pass


class AsyncConfigProvider:
    def __init__(
        self,
        *,
        env_prefix: str = "VER9_",
    ) -> None:
        self.env_prefix = env_prefix
        self._config: AppConfig | None = None

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            raise ConfigNotLoadedError("configuration has not been loaded")

        return self._config

    async def load_config(self, config_path: str) -> AppConfig:
        path = Path(config_path)
        raw = await asyncio.to_thread(path.read_bytes)
        payload = self._decode_payload(path, raw)
        self._apply_environment_overrides(payload)
        self._config = msgspec.convert(payload, type=AppConfig, strict=True)
        return self._config

    def _decode_payload(
        self,
        path: Path,
        raw: bytes,
    ) -> dict[str, object]:
        suffix = path.suffix.lower()

        if suffix == ".json":
            payload = msgspec.json.decode(raw)
        elif suffix == ".toml":
            payload = tomllib.loads(raw.decode("utf-8"))
        else:
            raise ConfigError(
                f"unsupported config format: {path.suffix}; expected .json or .toml"
            )

        if not isinstance(payload, dict):
            raise ConfigError("configuration root must be an object")

        return payload

    def _apply_environment_overrides(
        self,
        payload: dict[str, object],
    ) -> None:
        overrides = (
            ("ENVIRONMENT", ("environment",), str),
            ("DEBUG", ("debug",), self._parse_bool),
            ("EXCHANGE_API_KEY", ("exchange", "api_key"), str),
            ("EXCHANGE_SECRET_KEY", ("exchange", "secret_key"), str),
            ("EXCHANGE_RATE_LIMIT_MS", ("exchange", "rate_limit_ms"), int),
            ("EXCHANGE_SANDBOX", ("exchange", "sandbox"), self._parse_bool),
            (
                "PERSISTENCE_LOG_ROTATION_BYTES",
                ("persistence", "log_rotation_bytes"),
                int,
            ),
            (
                "PERSISTENCE_SNAPSHOT_INTERVAL_SECONDS",
                ("persistence", "snapshot_interval_seconds"),
                int,
            ),
            ("PERSISTENCE_BASE_DIR", ("persistence", "base_dir"), str),
            ("RISK_MAX_DRAWDOWN", ("risk", "max_drawdown"), float),
            ("RISK_MAX_POSITION_SIZE", ("risk", "max_position_size"), float),
            (
                "RISK_BLOCKED_ASSETS",
                ("risk", "blocked_assets"),
                self._parse_csv_tuple,
            ),
        )

        for env_name, path, parser in overrides:
            raw_value = os.environ.get(f"{self.env_prefix}{env_name}")

            if raw_value is None:
                continue

            self._set_nested_value(
                payload=payload,
                path=path,
                value=parser(raw_value),
            )

    def _set_nested_value(
        self,
        *,
        payload: dict[str, object],
        path: tuple[str, ...],
        value: object,
    ) -> None:
        current: dict[str, object] = payload

        for key in path[:-1]:
            existing = current.get(key)

            if not isinstance(existing, dict):
                existing = {}
                current[key] = existing

            current = existing

        current[path[-1]] = value

    def _parse_bool(self, value: str) -> bool:
        normalized = value.strip().lower()

        if normalized in {"1", "true", "yes", "on"}:
            return True

        if normalized in {"0", "false", "no", "off"}:
            return False

        raise ConfigError(f"invalid boolean environment override: {value}")

    def _parse_csv_tuple(self, value: str) -> tuple[str, ...]:
        return tuple(
            item.strip()
            for item in value.split(",")
            if item.strip()
        )
