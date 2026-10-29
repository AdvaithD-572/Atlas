import json
import re
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ATLAS_", extra="forbid", hide_input_in_errors=True
    )

    database_path: Path = Path(".local/atlas.db")
    credentials_path: Path = Path(".local/credentials.json")
    token_hashes: dict[str, str] = Field(default_factory=dict, repr=False)
    max_upload_bytes: int = Field(default=262144, ge=1024, le=1048576)
    chunk_size: int = Field(default=800, ge=64, le=4000)
    chunk_overlap: int = Field(default=120, ge=0)
    max_documents: int = Field(default=100, ge=1, le=1000)
    max_owner_chars: int = Field(default=2000000, ge=1024, le=10000000)
    requests_per_minute: int = Field(default=120, ge=1, le=10000)
    postgres_dsn: SecretStr | None = Field(default=None, repr=False)
    postgres_dsn_path: Path | None = None
    generation_enabled: bool = False
    vector_enabled: bool = False
    embedding_model: str = Field(default="all-minilm:latest", min_length=1, max_length=100)
    generation_model: str = Field(default="qwen3:1.7b", min_length=1, max_length=100)
    ollama_url: str = "http://127.0.0.1:11434"
    frontend_dir: Path | None = None

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        if self.postgres_dsn_path is not None:
            if self.postgres_dsn is not None:
                raise ValueError("Configure a PostgreSQL DSN or DSN file, not both.")
            try:
                self.postgres_dsn = SecretStr(self.postgres_dsn_path.read_text().strip())
            except OSError:
                raise ValueError("PostgreSQL DSN file is unavailable.") from None
        if self.vector_enabled and self.postgres_dsn is None:
            raise ValueError("Vector retrieval requires PostgreSQL.")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be smaller than chunk size.")
        if self.chunk_overlap > self.chunk_size // 2:
            raise ValueError("Chunk overlap cannot exceed half of chunk size.")
        if not self.token_hashes:
            try:
                loaded = json.loads(self.credentials_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError("Provision credentials before starting Atlas.") from exc
            if not isinstance(loaded, dict):
                raise ValueError("Credentials must be an owner-to-digest mapping.")
            self.token_hashes = loaded
        if not 1 <= len(self.token_hashes) <= 100:
            raise ValueError("Configure between one and 100 principals.")
        for owner, digest in self.token_hashes.items():
            if not isinstance(owner, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", owner):
                raise ValueError("Invalid principal identifier.")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Credentials must contain SHA-256 digests, not raw tokens.")
        if len(set(self.token_hashes.values())) != len(self.token_hashes):
            raise ValueError("Each principal must have a distinct credential.")
        return self
