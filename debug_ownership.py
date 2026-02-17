#!/usr/bin/env python3
"""Debug script to check character ownership."""
from server.db import engine, Character, User
from sqlmodel import Session, select

with Session(engine) as session:
    chars = session.exec(select(Character)).all()
    users = session.exec(select(User)).all()
    
    print("=== Characters ===")
    for c in chars:
        print(f"ID: {c.id}, Name: {c.name}, Owner: {c.owner_id}")
    
    print("\n=== Users ===")
    for u in users:
        print(f"ID: {u.id}, Email: {u.email}, Admin: {getattr(u, 'admin', False)}")
