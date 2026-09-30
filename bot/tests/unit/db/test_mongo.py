import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.mongo import (
    get_client,
    get_db,
    close_mongo_client,
    init_db_indexes,
    COLLECTION_TRACKED_WALLETS,
    COLLECTION_TOKEN_SIGNALS,
    COLLECTION_FOMO_SESSIONS,
    COLLECTION_ACTIVE_POSITIONS,
    COLLECTION_PERFORMANCE_LEDGER,
)


@pytest.fixture(autouse=True)
def cleanup_client():
    close_mongo_client()
    yield
    close_mongo_client()


def test_get_client_singleton():
    with patch("app.db.mongo.AsyncIOMotorClient") as mock_motor:
        mock_instance = MagicMock()
        mock_motor.return_value = mock_instance

        client1 = get_client("mongodb://localhost:27017")
        client2 = get_client("mongodb://localhost:27017")

        assert client1 is client2
        assert mock_motor.call_count == 1
        mock_motor.assert_called_with("mongodb://localhost:27017")


def test_get_db():
    with patch("app.db.mongo.AsyncIOMotorClient") as mock_motor:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_motor.return_value = mock_client

        db = get_db("mongodb://localhost:27017", "tracking_meme")
        assert db is mock_db
        mock_client.__getitem__.assert_called_with("tracking_meme")


@pytest.mark.asyncio
async def test_init_db_indexes():
    mock_db = MagicMock()
    mock_collections = {
        COLLECTION_TRACKED_WALLETS: MagicMock(),
        COLLECTION_TOKEN_SIGNALS: MagicMock(),
        COLLECTION_FOMO_SESSIONS: MagicMock(),
        COLLECTION_ACTIVE_POSITIONS: MagicMock(),
        COLLECTION_PERFORMANCE_LEDGER: MagicMock(),
    }

    for name, col in mock_collections.items():
        col.create_index = AsyncMock()
        mock_db.__getitem__.side_effect = lambda n, cols=mock_collections: cols.get(n, MagicMock())

    await init_db_indexes(mock_db)

    # Verify tracked_wallets indexes
    tracked_col = mock_collections[COLLECTION_TRACKED_WALLETS]
    assert tracked_col.create_index.call_count >= 3
    tracked_calls = [call.args for call in tracked_col.create_index.call_args_list]
    assert ([("chain", 1), ("score", -1)],) in tracked_calls

    # Verify token_signals indexes
    signals_col = mock_collections[COLLECTION_TOKEN_SIGNALS]
    assert signals_col.create_index.call_count >= 3
    signals_calls = [call.args for call in signals_col.create_index.call_args_list]
    assert ([("token_address", 1), ("chain", 1)],) in signals_calls

    # Verify active_positions index
    positions_col = mock_collections[COLLECTION_ACTIVE_POSITIONS]
    assert positions_col.create_index.call_count >= 1

    # Verify performance_ledger index
    ledger_col = mock_collections[COLLECTION_PERFORMANCE_LEDGER]
    assert ledger_col.create_index.call_count >= 1
