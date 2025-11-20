#!/usr/bin/env python3
"""
Migration script to add trace_id column to user_activities table.
This handles both SQLite and PostgreSQL databases.
"""
import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./legacy_data.db")

def migrate_sqlite(engine):
    """Add trace_id column to SQLite database"""
    conn = engine.raw_connection()
    cursor = conn.cursor()
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(user_activities)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'trace_id' not in columns:
            print("Adding trace_id column to user_activities table...")
            cursor.execute("ALTER TABLE user_activities ADD COLUMN trace_id VARCHAR")
            
            # Create index if it doesn't exist
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_user_activities_trace_id 
                ON user_activities(trace_id)
            """)
            
            conn.commit()
            print("✅ Successfully added trace_id column and index")
        else:
            print("✅ trace_id column already exists")
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def migrate_postgresql(engine):
    """Add trace_id column to PostgreSQL database"""
    with engine.connect() as conn:
        try:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'user_activities' 
                AND column_name = 'trace_id'
            """))
            
            if result.fetchone() is None:
                print("Adding trace_id column to user_activities table...")
                conn.execute(text("""
                    ALTER TABLE user_activities 
                    ADD COLUMN trace_id VARCHAR
                """))
                
                # Create index if it doesn't exist
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_user_activities_trace_id 
                    ON user_activities(trace_id)
                """))
                
                conn.commit()
                print("✅ Successfully added trace_id column and index")
            else:
                print("✅ trace_id column already exists")
        except Exception as e:
            print(f"❌ Error: {e}")
            conn.rollback()
            raise

def main():
    """Run the migration"""
    print(f"Connecting to database: {SQLALCHEMY_DATABASE_URL.split('@')[-1] if '@' in SQLALCHEMY_DATABASE_URL else SQLALCHEMY_DATABASE_URL}")
    
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        # SQLite-specific connection args
        engine = create_engine(
            SQLALCHEMY_DATABASE_URL,
            connect_args={"check_same_thread": False}
        )
        migrate_sqlite(engine)
    else:
        # PostgreSQL or other databases
        engine = create_engine(SQLALCHEMY_DATABASE_URL)
        migrate_postgresql(engine)
    
    print("Migration complete!")

if __name__ == "__main__":
    main()

