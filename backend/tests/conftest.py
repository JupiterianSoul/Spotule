import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://spotule:spotule@localhost:5432/spotule")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg://spotule:spotule@localhost:5432/spotule")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/9")
os.environ.setdefault("SECRET_KEY", "test-secret")
