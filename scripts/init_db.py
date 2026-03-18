#!/usr/bin/env python3
"""Initialize PostgreSQL database for RAG knowledge base.

This script creates the necessary database, extensions, and tables.

Usage:
    uv run python scripts/init_db.py

Prerequisites:
    1. PostgreSQL server running
    2. pgvector extension installed
    3. Database user with CREATE DATABASE privileges
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import asyncpg

from omni_agent.core.config import settings


async def create_database() -> None:
    """Create the database if it doesn't exist."""
    # Connect to default postgres database
    conn = await asyncpg.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database="postgres",
    )

    try:
        # Check if database exists
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            settings.POSTGRES_DB,
        )

        if not exists:
            # Create database
            await conn.execute(f'CREATE DATABASE "{settings.POSTGRES_DB}"')
            print(f"✅ Created database: {settings.POSTGRES_DB}")
        else:
            print(f"ℹ️  Database already exists: {settings.POSTGRES_DB}")
    finally:
        await conn.close()


async def init_schema() -> None:
    """Initialize database schema with pgvector extension and tables."""
    # Connect to our database
    conn = await asyncpg.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
    )

    try:
        # Enable pgvector extension
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        print("✅ pgvector extension enabled")

        # Create documents table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                filename VARCHAR(500) NOT NULL,
                file_type VARCHAR(50) NOT NULL,
                file_size INTEGER NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                metadata JSONB DEFAULT '{}'
            )
        """)
        print("✅ Created documents table")

        # Create chunks table with vector column
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS chunks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                embedding vector({settings.EMBEDDING_DIMENSION}),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                metadata JSONB DEFAULT '{{}}'
            )
        """)
        print("✅ Created chunks table")

        # Create indexes
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_document_id
            ON chunks(document_id)
        """)
        print("✅ Created document_id index")

        # Create vector similarity index
        # Check if there are any rows first (IVFFlat needs data)
        row_count = await conn.fetchval("SELECT COUNT(*) FROM chunks")
        if row_count > 0:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding
                ON chunks USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)
            print("✅ Created vector similarity index")
        else:
            print("ℹ️  Skipping vector index (no data yet, will be created on first insert)")

        print("\n✅ Database initialization complete!")

    finally:
        await conn.close()


async def main() -> None:
    """Main entry point."""
    print("=" * 50)
    print("RAG Knowledge Base - Database Initialization")
    print("=" * 50)
    print(f"Host: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}")
    print(f"Database: {settings.POSTGRES_DB}")
    print(f"User: {settings.POSTGRES_USER}")
    print(f"Embedding dimension: {settings.EMBEDDING_DIMENSION}")
    print("=" * 50)

    try:
        await create_database()
        await init_schema()
    except asyncpg.InvalidCatalogNameError:
        print("❌ Database connection failed. Make sure PostgreSQL is running.")
        sys.exit(1)
    except asyncpg.InvalidPasswordError:
        print("❌ Authentication failed. Check your POSTGRES_PASSWORD.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
