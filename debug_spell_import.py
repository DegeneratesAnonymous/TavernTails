#!/usr/bin/env python3
"""Debug script to check spell import for a character."""
from server.db import engine, Character
from sqlmodel import Session, select
import json

with Session(engine) as session:
    # Get the most recent character
    chars = session.exec(select(Character).order_by(Character.id.desc()).limit(5)).all()
    
    for c in chars:
        sheet = c.sheet or {}
        spells = sheet.get("spells", [])
        spellbook = sheet.get("spellbook", [])
        raw_text = sheet.get("raw_text", "")
        
        print(f"\n=== Character {c.id}: {c.name} ===")
        print(f"Flat spells count: {len(spells)}")
        print(f"Spellbook entries count: {len(spellbook)}")
        
        if spells:
            print(f"\nFirst 10 flat spells:")
            for i, s in enumerate(spells[:10]):
                print(f"  {i+1}. {s}")
        
        if spellbook:
            print(f"\nFirst 3 spellbook entries:")
            for i, entry in enumerate(spellbook[:3]):
                print(f"  {i+1}. {json.dumps(entry, indent=4)}")
        
        if raw_text:
            print(f"\nRaw text sample (first 500 chars):")
            print(raw_text[:500])
            print("\n---")
            # Look for spell table indicators
            if "SPELL NAME" in raw_text.upper():
                print("✓ Found 'SPELL NAME' in raw text")
            if "SOURCE" in raw_text.upper():
                print("✓ Found 'SOURCE' in raw text")
            if "CANTRIP" in raw_text.upper():
                print("✓ Found 'CANTRIP' in raw text")
