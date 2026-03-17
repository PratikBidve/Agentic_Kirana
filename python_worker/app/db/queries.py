"""All raw asyncpg queries — single source of truth for DB access."""
from typing import Optional
import asyncpg


async def find_product_by_name(
    pool: asyncpg.Pool,
    store_id: str,
    name: str,
) -> Optional[dict]:
    """
    Exact name match first, then alias substring match.
    Always scoped to store_id — no cross-store leakage.
    """
    row = await pool.fetchrow(
        """
        SELECT id, name, current_stock, unit, selling_price, reorder_level, name_aliases
        FROM product
        WHERE store_id = $1
          AND is_active = true
          AND (
            lower(name) = lower($2)
            OR lower(name_aliases) LIKE lower($3)
          )
        LIMIT 1
        """,
        store_id, name, f"%{name}%",
    )
    return dict(row) if row else None


async def find_customer_by_name(
    pool: asyncpg.Pool,
    store_id: str,
    name: str,
) -> Optional[dict]:
    row = await pool.fetchrow(
        """
        SELECT id, name, phone, total_outstanding
        FROM customer
        WHERE store_id = $1
          AND lower(name) LIKE lower($2)
        LIMIT 1
        """,
        store_id, f"%{name}%",
    )
    return dict(row) if row else None


async def list_all_products(
    pool: asyncpg.Pool,
    store_id: str,
) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT name, current_stock, unit, reorder_level
        FROM product
        WHERE store_id = $1 AND is_active = true
        ORDER BY name
        """,
        store_id,
    )
    return [dict(r) for r in rows]


async def list_low_stock_products(
    pool: asyncpg.Pool,
    store_id: str,
) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT name, current_stock, unit, reorder_level
        FROM product
        WHERE store_id = $1
          AND is_active = true
          AND reorder_level IS NOT NULL
          AND reorder_level > 0
          AND current_stock <= reorder_level
        ORDER BY current_stock ASC
        """,
        store_id,
    )
    return [dict(r) for r in rows]


async def insert_staged_khata_entry(
    pool: asyncpg.Pool,
    entry_id: str,
    store_id: str,
    customer_id: str,
    amount: str,
    note: str,
) -> None:
    await pool.execute(
        """
        INSERT INTO khata_entry
          (id, store_id, customer_id, amount, note, confirmed_by_owner, created_at)
        VALUES ($1, $2, $3, $4, $5, false, NOW())
        """,
        entry_id, store_id, customer_id, amount, note,
    )


async def update_job_status(
    pool: asyncpg.Pool,
    job_id: str,
    status: str,
    output: Optional[str] = None,
    error: Optional[str] = None,
    agent_steps: Optional[str] = None,
) -> None:
    await pool.execute(
        """
        UPDATE agent_job
        SET status = $1,
            output = $2,
            error_message = $3,
            agent_steps = $4,
            updated_at = NOW()
        WHERE id = $5
        """,
        status, output, error, agent_steps, job_id,
    )


async def find_store_by_phone(
    pool: asyncpg.Pool,
    phone: str,
) -> Optional[dict]:
    row = await pool.fetchrow(
        "SELECT id FROM store WHERE phone = $1 LIMIT 1",
        phone,
    )
    return dict(row) if row else None


async def insert_agent_job(
    pool: asyncpg.Pool,
    job_id: str,
    store_id: str,
    text: str,
) -> None:
    await pool.execute(
        """
        INSERT INTO agent_job (id, store_id, input, status, created_at, updated_at)
        VALUES ($1, $2, $3, 'pending', NOW(), NOW())
        """,
        job_id, store_id, text,
    )
