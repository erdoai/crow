"""Tests for the agent store — set, append, get round-trip.

Hits the real database (CROW_DATABASE_URL) to catch serialization
issues like the JSONB double-encoding bug.
"""

import os

import pytest
import pytest_asyncio

from crow.db.database import Database

DB_URL = os.environ.get("CROW_DATABASE_URL")
NS = "_test_store"
USER = "_test_user"


@pytest_asyncio.fixture
async def db():
    if not DB_URL:
        pytest.skip("CROW_DATABASE_URL not set")
    database = await Database.connect(DB_URL)
    yield database
    # Cleanup test data
    await database._pool.execute(
        "DELETE FROM agent_store WHERE namespace = $1", NS
    )
    await database.close()


@pytest.mark.asyncio
async def test_store_set_list_roundtrip(db):
    """store_set with a list should store a JSONB array, not a string."""
    data = [{"company": "Acme", "role": "Engineer"}]
    row = await db.store_set(NS, "leads", data, user_id=USER)

    assert isinstance(row["data"], list), (
        f"Expected list, got {type(row['data']).__name__}: {row['data']!r}"
    )
    assert row["data"] == data


@pytest.mark.asyncio
async def test_store_set_empty_list(db):
    """store_set with [] should store a JSONB empty array, not '[]' string."""
    row = await db.store_set(NS, "leads", [], user_id=USER)

    assert isinstance(row["data"], list), (
        f"Expected list, got {type(row['data']).__name__}: {row['data']!r}"
    )
    assert row["data"] == []


@pytest.mark.asyncio
async def test_store_append_to_empty(db):
    """store_append on a non-existent key should create an array."""
    items = [{"company": "Foo"}, {"company": "Bar"}]
    row = await db.store_append(NS, "new_key", items, user_id=USER)

    assert isinstance(row["data"], list)
    assert len(row["data"]) == 2
    assert row["data"][0]["company"] == "Foo"


@pytest.mark.asyncio
async def test_store_append_to_existing(db):
    """store_append on an existing array should concatenate."""
    await db.store_set(NS, "leads", [{"id": 1}], user_id=USER)
    row = await db.store_append(NS, "leads", [{"id": 2}], user_id=USER)

    assert isinstance(row["data"], list)
    assert len(row["data"]) == 2
    assert row["data"][0]["id"] == 1
    assert row["data"][1]["id"] == 2


@pytest.mark.asyncio
async def test_store_append_to_non_array_resets(db):
    """store_append on a non-array value should replace with items."""
    # Simulate the bug: data is a string
    await db._pool.execute(
        """INSERT INTO agent_store (namespace, key, user_id, data)
           VALUES ($1, $2, $3, $4::jsonb)
           ON CONFLICT (namespace, key, user_id)
           DO UPDATE SET data = $4::jsonb""",
        NS, "bad_key", USER, '"old string"',
    )
    row = await db.store_append(NS, "bad_key", [{"new": True}], user_id=USER)

    assert isinstance(row["data"], list), (
        f"Expected list after append to non-array, got {type(row['data']).__name__}"
    )
    assert row["data"] == [{"new": True}]


@pytest.mark.asyncio
async def test_store_get_returns_correct_type(db):
    """store_get should return the same type that was stored."""
    await db.store_set(NS, "leads", [{"a": 1}], user_id=USER)
    row = await db.store_get(NS, "leads", user_id=USER)

    assert row is not None
    assert isinstance(row["data"], list), (
        f"store_get returned {type(row['data']).__name__} instead of list"
    )


@pytest.mark.asyncio
async def test_full_roundtrip(db):
    """Full flow: set empty → append → append → get."""
    await db.store_set(NS, "leads", [], user_id=USER)
    await db.store_append(NS, "leads", [{"id": 1}], user_id=USER)
    await db.store_append(NS, "leads", [{"id": 2}, {"id": 3}], user_id=USER)

    row = await db.store_get(NS, "leads", user_id=USER)
    assert row is not None
    assert isinstance(row["data"], list)
    assert len(row["data"]) == 3
    assert [d["id"] for d in row["data"]] == [1, 2, 3]
