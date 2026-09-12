"""How many rows an INSERT … ON CONFLICT DO NOTHING actually wrote."""

from __future__ import annotations

from sqlalchemy.engine import Result


def inserted_count(result: Result) -> int:
    """Count the rows a conflict-tolerant insert really added.

    `rowcount` cannot answer this. psycopg reports -1 for a multi-row INSERT, because
    SQLAlchemy sends it through the executemany path, which surfaces no count — so the
    scheduler reported "streams_inserted: -1" and the ZIP importer would have recorded a
    negative insert count and one duplicate more than the batch even held. asyncpg happens
    to report it correctly, which is exactly why this was invisible in development and wrong
    in production.

    Pair this with `.returning(<primary key>)` on the statement. Both drivers answer that
    exactly, and ON CONFLICT DO NOTHING returns a row only for what it genuinely inserted,
    so the count stays right whether every row was new, every row was a duplicate, or the
    batch was a mixture.
    """
    return len(result.scalars().all())
