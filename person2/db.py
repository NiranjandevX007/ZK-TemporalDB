"""
ZK-TemporalDB — Database Connection Management
Handles PostgreSQL (psycopg2) and MongoDB (PyMongo) connections.

Connection strings are read from environment variables or .env file.
Never hardcode credentials.

Usage:
    from person2.db import get_pg_connection, get_mongo_db

    pg_conn = get_pg_connection()
    mongo_db = get_mongo_db()
"""

import os
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

def _load_env():
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        # Search for .env in person2/ first, then project root
        env_paths = [
            os.path.join(os.path.dirname(__file__), '.env'),
            os.path.join(os.path.dirname(__file__), '..', '.env'),
        ]
        for path in env_paths:
            if os.path.exists(path):
                load_dotenv(path)
                logger.info("Loaded environment from %s", path)
                return
    except ImportError:
        pass

_load_env()


def get_pg_uri() -> str:
    """Return the PostgreSQL connection URI from environment."""
    uri = os.environ.get('POSTGRES_URI')
    if not uri:
        # Fallback for local development: connect as current user
        db_name = os.environ.get('POSTGRES_DB', 'zk_temporaldb')
        uri = f'postgresql://localhost:5432/{db_name}'
        logger.info("POSTGRES_URI not set, using default: %s", uri)
    return uri


def get_mongo_uri() -> str:
    """Return the MongoDB connection URI from environment."""
    return os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')


def get_mongo_db_name() -> str:
    """Return the MongoDB database name from environment."""
    return os.environ.get('MONGO_DB_NAME', 'zk_temporaldb')


# ── PostgreSQL ────────────────────────────────────────────────────────────────

def get_pg_connection():
    """
    Create and return a new psycopg2 connection.
    Caller is responsible for closing it.

    Raises:
        psycopg2.OperationalError: if the database is unreachable.
    """
    import psycopg2
    import psycopg2.extras

    uri = get_pg_uri()
    conn = psycopg2.connect(uri)
    conn.set_session(autocommit=False)
    return conn


@contextmanager
def pg_cursor(conn=None):
    """
    Context manager yielding a psycopg2 cursor.
    If no connection is provided, creates one and closes it on exit.
    On success commits; on error rolls back.
    """
    import psycopg2.extras

    own_conn = conn is None
    if own_conn:
        conn = get_pg_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        if own_conn:
            conn.commit()
    except Exception:
        if own_conn:
            conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()


# ── MongoDB ───────────────────────────────────────────────────────────────────

_mongo_client = None

def get_mongo_client():
    """
    Return a shared MongoClient instance.
    Creates the client on first call.

    Raises:
        pymongo.errors.ConnectionFailure: if MongoDB is unreachable.
    """
    global _mongo_client
    if _mongo_client is None:
        from pymongo import MongoClient
        uri = get_mongo_uri()
        _mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # Verify connectivity
        _mongo_client.admin.command('ping')
        logger.info("Connected to MongoDB at %s", uri)
    return _mongo_client


def get_mongo_db():
    """
    Return the MongoDB database object for ZK-TemporalDB.
    """
    client = get_mongo_client()
    return client[get_mongo_db_name()]


def close_mongo():
    """Close the shared MongoDB client if open."""
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None


# ── Health Checks ─────────────────────────────────────────────────────────────

def check_pg() -> dict:
    """Test PostgreSQL connectivity. Returns status dict."""
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        conn.close()
        return {"status": "ok", "version": version}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_mongo() -> dict:
    """Test MongoDB connectivity. Returns status dict."""
    try:
        client = get_mongo_client()
        info = client.server_info()
        return {"status": "ok", "version": info.get("version", "unknown")}
    except Exception as e:
        return {"status": "error", "error": str(e)}
