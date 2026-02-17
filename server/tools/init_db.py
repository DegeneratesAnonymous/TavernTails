#!/usr/bin/env python3
"""Initialize database tables from SQLModel metadata."""
import os
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlmodel import SQLModel

# Import all models to ensure they're registered with SQLModel.metadata
from server import db  # noqa: F401

# Get database URL from environment or use default
db_url = os.getenv("TAVERNTAILS_DATABASE_URL", "sqlite:///./taverntails.db")
engine = create_engine(db_url, echo=False)

print(f"Creating tables in database: {db_url}")
SQLModel.metadata.create_all(engine)
print("✓ Database tables created successfully")
