-- Install pgvector on template1 so every future CREATE DATABASE inherits it.
-- This script runs automatically on first Postgres container startup.
CREATE EXTENSION IF NOT EXISTS vector;
