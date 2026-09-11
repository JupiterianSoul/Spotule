import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://spotimax:spotimax@localhost:5432/spotimax")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg://spotimax:spotimax@localhost:5432/spotimax")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/9")
os.environ.setdefault("SECRET_KEY", "test-secret")
