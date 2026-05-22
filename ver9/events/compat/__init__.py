"""Compatibility translators for legacy -> domain event migration.

This module provides functions to translate legacy runtime event types
into canonical domain event types. These translators:

1. Extract fields from legacy events
2. Map them to domain event fields
3. Supply defaults where legacy data is missing
4. Return immutable domain dataclass instances

All translation is explicit and type-safe. No silent schema mutations.
"""
