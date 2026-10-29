from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Document(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_key: str
    version: int
    content_hash: str
    media_type: str
    parser_version: str
    chunk_size: int
    chunk_overlap: int
    embedding_model: None = None
    status: Literal["indexed"]
    created_at: str
    updated_at: str
    chunk_count: int
    normalization: Literal["none-v1", "pdf-text-v1", "html-text-v1"] = "none-v1"

    @model_validator(mode="after")
    def source_normalization(self) -> Self:
        if self.media_type == "application/pdf":
            self.normalization = "pdf-text-v1"
        elif self.media_type == "text/html":
            self.normalization = "html-text-v1"
        else:
            self.normalization = "none-v1"
        return self


class Passage(BaseModel):
    id: str
    document_id: str
    source_key: str
    version: int
    ordinal: int
    start: int
    end: int
    text: str
    page_number: int | None = Field(default=None, ge=1, le=200)
    heading: str | None = Field(default=None, max_length=512)


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class Health(BaseModel):
    status: Literal["live", "ready"]
