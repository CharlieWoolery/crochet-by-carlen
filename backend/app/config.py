import os
from pathlib import Path

from pydantic import BaseModel


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv(Path(__file__).parent.parent / ".env")


class Settings(BaseModel):
    database_url: str


def get_settings() -> Settings:
    return Settings(database_url=os.environ["DATABASE_URL"])


settings = get_settings()
