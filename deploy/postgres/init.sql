-- Runs once on first Postgres boot (docker-entrypoint-initdb.d).
-- Enables pgvector and creates the three logical schemas that keep the two
-- agents' data separated (Requirement #1: "separate databases").

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS business;
CREATE SCHEMA IF NOT EXISTS health;

-- Tables themselves are created by `python -m aia.db.init` (SQLAlchemy metadata),
-- which is idempotent and also re-creates these objects if missing.
