"""
Database layer - SQLite via aiosqlite for async job tracking.
"""

import aiosqlite
import json
import uuid
from datetime import datetime
from typing import Optional


DB_PATH = "neural_agency.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                brief TEXT NOT NULL,
                strategy TEXT,
                copy_assets TEXT,
                social_content TEXT,
                seo_content TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        await db.commit()


async def create_job(brief: dict) -> str:
    job_id = str(uuid.uuid4())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO jobs (id, status, brief, created_at)
               VALUES (?, ?, ?, ?)""",
            (job_id, "pending", json.dumps(brief), datetime.utcnow().isoformat()),
        )
        await db.commit()
    return job_id


async def update_job_status(job_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET status = ? WHERE id = ?", (status, job_id)
        )
        await db.commit()


async def save_job_results(job_id: str, results: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE jobs SET
                status = 'completed',
                strategy = ?,
                copy_assets = ?,
                social_content = ?,
                seo_content = ?,
                completed_at = ?
               WHERE id = ?""",
            (
                results.get("strategy"),
                results.get("copy_assets"),
                results.get("social_content"),
                results.get("seo_content"),
                datetime.utcnow().isoformat(),
                job_id,
            ),
        )
        await db.commit()


async def save_job_error(job_id: str, error: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET status = 'failed', error = ? WHERE id = ?",
            (error, job_id),
        )
        await db.commit()


async def get_job(job_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)


async def get_all_jobs() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, status, brief, created_at, completed_at FROM jobs ORDER BY created_at DESC LIMIT 50"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
