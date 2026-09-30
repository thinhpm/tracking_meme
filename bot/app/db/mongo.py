"""MongoDB async client connection and index management using motor."""
from __future__ import annotations

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

logger = logging.getLogger(__name__)

COLLECTION_TRACKED_WALLETS = "tracked_wallets"
COLLECTION_TOKEN_SIGNALS = "token_signals"
COLLECTION_FOMO_SESSIONS = "fomo_sessions"
COLLECTION_ACTIVE_POSITIONS = "active_positions"
COLLECTION_PERFORMANCE_LEDGER = "performance_ledger"

_client: Optional[AsyncIOMotorClient] = None


def get_client(uri: Optional[str] = None) -> AsyncIOMotorClient:
    """Return singleton AsyncIOMotorClient instance."""
    global _client
    if _client is None:
        target_uri = uri or get_settings().mongodb_uri
        logger.info("Initializing MongoDB client", extra={"uri": target_uri})
        _client = AsyncIOMotorClient(target_uri)
    return _client


def get_db(uri: Optional[str] = None, db_name: Optional[str] = None) -> AsyncIOMotorDatabase:
    """Return AsyncIOMotorDatabase instance from singleton client."""
    client = get_client(uri)
    target_db_name = db_name or get_settings().mongodb_db_name
    return client[target_db_name]


def close_mongo_client() -> None:
    """Close singleton client connection if initialized."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


async def init_db_indexes(db: AsyncIOMotorDatabase) -> None:
    """Initialize necessary compound and TTL indexes across collections."""
    logger.info("Creating MongoDB indexes...")

    # 1. tracked_wallets
    tracked_col = db[COLLECTION_TRACKED_WALLETS]
    await tracked_col.create_index([("chain", 1), ("score", -1)])
    await tracked_col.create_index([("fomo_handle", 1)], sparse=True)
    await tracked_col.create_index([("provenance.parent_funder", 1)])

    # 2. token_signals
    signals_col = db[COLLECTION_TOKEN_SIGNALS]
    await signals_col.create_index([("token_address", 1), ("chain", 1)], unique=True)
    await signals_col.create_index([("composite_score", -1), ("created_at", -1)])
    await signals_col.create_index([("created_at", 1)], expireAfterSeconds=2592000)  # 30-day TTL

    # 3. fomo_sessions
    sessions_col = db[COLLECTION_FOMO_SESSIONS]
    await sessions_col.create_index([("_id", 1)])

    # 4. active_positions
    positions_col = db[COLLECTION_ACTIVE_POSITIONS]
    await positions_col.create_index([("status", 1)])
    await positions_col.create_index([("token_address", 1), ("status", 1)])

    # 5. performance_ledger
    ledger_col = db[COLLECTION_PERFORMANCE_LEDGER]
    await ledger_col.create_index([("roi_percent", -1)])
    await ledger_col.create_index([("created_at", -1)])

    logger.info("MongoDB indexes created successfully")
