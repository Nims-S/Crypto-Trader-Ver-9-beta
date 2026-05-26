"""Phase 5b: Idempotency Layer - Duplicate Suppression.

Responsibilities:
1. Track processed execution IDs
2. Suppress duplicate fills (websocket retries)
3. Survive reconnections
4. Support bounded cache with TTL
5. Enable replay-safe deduplication

Properties:
- Deterministic deduplication
- Replay-safe (same input → same output)
- Bounded memory (LRU or TTL eviction)
- Distributed-ready (can be externalized)
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from time import time_ns
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ver9.domain.events.execution import FillReceivedDomain


@dataclass(frozen=True, slots=True)
class ExecutionHash:
    """Fingerprint for deduplication.
    
    Combines exchange, order, and fill details to identify duplicates.
    """
    
    exchange: str
    exchange_order_id: str
    trade_id: str
    fill_price: float
    fill_quantity: float
    
    def to_hash(self) -> str:
        """Create deterministic hash for comparison."""
        payload = f"{self.exchange}:{self.exchange_order_id}:{self.trade_id}:{self.fill_price}:{self.fill_quantity}"
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """Immutable record of processed execution."""
    
    execution_hash: str
    first_seen_ns: int
    last_seen_ns: int
    duplicate_count: int = 0  # Times we've rejected this duplicate


class IdempotencyLayer:
    """Deduplication cache for exchange fill events.
    
    Prevents duplicate fill processing from:
    - Websocket retransmissions
    - Connection recovery replays
    - Multiple event bus subscribers
    
    Thread-safe and replay-safe.
    """

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 100_000) -> None:
        """Initialize idempotency cache.
        
        Args:
            ttl_seconds: Time-to-live for cache entries (3600 = 1 hour)
            max_entries: Maximum cached executions before eviction
        """
        self._ttl_ns = ttl_seconds * 1_000_000_000
        self._max_entries = max_entries
        self._lock = asyncio.Lock()
        self._cache: dict[str, IdempotencyRecord] = {}
        self._access_order: list[str] = []  # LRU tracking

    async def is_duplicate(self, event: FillReceivedDomain) -> bool:
        """Check if fill is duplicate (already processed).
        
        Args:
            event: FillReceivedDomain to check
            
        Returns:
            True if duplicate (should skip), False if new
        """
        async with self._lock:
            hash_obj = ExecutionHash(
                exchange=event.exchange,
                exchange_order_id=event.exchange_order_id,
                trade_id=event.execution_id,
                fill_price=event.price,
                fill_quantity=event.quantity,
            )
            hash_str = hash_obj.to_hash()
            
            # Check cache
            if hash_str in self._cache:
                record = self._cache[hash_str]
                
                # Update last seen and duplicate count
                updated_record = IdempotencyRecord(
                    execution_hash=record.execution_hash,
                    first_seen_ns=record.first_seen_ns,
                    last_seen_ns=time_ns(),
                    duplicate_count=record.duplicate_count + 1,
                )
                self._cache[hash_str] = updated_record
                
                # Update LRU
                if hash_str in self._access_order:
                    self._access_order.remove(hash_str)
                self._access_order.append(hash_str)
                
                return True  # Duplicate
            
            # Not in cache - new execution
            return False

    async def record_execution(self, event: FillReceivedDomain) -> IdempotencyRecord:
        """Record newly processed execution.
        
        Args:
            event: FillReceivedDomain that was accepted
            
        Returns:
            Immutable record for tracking
        """
        async with self._lock:
            hash_obj = ExecutionHash(
                exchange=event.exchange,
                exchange_order_id=event.exchange_order_id,
                trade_id=event.execution_id,
                fill_price=event.price,
                fill_quantity=event.quantity,
            )
            hash_str = hash_obj.to_hash()
            
            # Create record
            now_ns = time_ns()
            record = IdempotencyRecord(
                execution_hash=hash_str,
                first_seen_ns=now_ns,
                last_seen_ns=now_ns,
                duplicate_count=0,
            )
            
            # Store in cache
            self._cache[hash_str] = record
            self._access_order.append(hash_str)
            
            # Evict expired and excess entries
            await self._evict_stale()
            await self._evict_lru()
            
            return record

    async def clear_expired(self) -> int:
        """Remove expired entries (older than TTL).
        
        Returns:
            Number of entries removed
        """
        async with self._lock:
            now_ns = time_ns()
            expired = [
                hash_str
                for hash_str, record in self._cache.items()
                if (now_ns - record.last_seen_ns) > self._ttl_ns
            ]
            
            for hash_str in expired:
                del self._cache[hash_str]
                if hash_str in self._access_order:
                    self._access_order.remove(hash_str)
            
            return len(expired)

    # ========================================================================
    # Private Helpers
    # ========================================================================

    async def _evict_stale(self) -> None:
        """Remove entries exceeding TTL."""
        now_ns = time_ns()
        stale = [
            hash_str
            for hash_str, record in self._cache.items()
            if (now_ns - record.last_seen_ns) > self._ttl_ns
        ]
        for hash_str in stale:
            del self._cache[hash_str]
            if hash_str in self._access_order:
                self._access_order.remove(hash_str)

    async def _evict_lru(self) -> None:
        """Remove least-recently-used entries if over max."""
        while len(self._cache) > self._max_entries and self._access_order:
            # Remove oldest accessed
            oldest_hash = self._access_order.pop(0)
            if oldest_hash in self._cache:
                del self._cache[oldest_hash]

    @property
    def cache_size(self) -> int:
        """Number of cached executions."""
        return len(self._cache)


class IdempotentFillProcessor:
    """Wrapper for fill event processing with deduplication.
    
    Applies idempotency check before delegating to downstream handlers.
    """

    def __init__(
        self,
        idempotency_layer: IdempotencyLayer,
        fill_handler,  # async callable
    ) -> None:
        """Initialize processor.
        
        Args:
            idempotency_layer: IdempotencyLayer for dedup
            fill_handler: Async callable that processes fill
        """
        self._idempotency = idempotency_layer
        self._handler = fill_handler

    async def process_fill(self, event: FillReceivedDomain) -> bool:
        """Process fill with idempotency check.
        
        Args:
            event: FillReceivedDomain to process
            
        Returns:
            True if processed (new), False if skipped (duplicate)
        """
        # Check if duplicate
        if await self._idempotency.is_duplicate(event):
            return False  # Skip processing
        
        try:
            # Process new fill
            await self._handler(event)
            
            # Record successful processing
            await self._idempotency.record_execution(event)
            
            return True  # Processed
            
        except Exception as exc:
            # Don't record failed processing (retry later)
            raise
