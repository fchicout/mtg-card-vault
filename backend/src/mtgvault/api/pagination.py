"""Shared pagination schema (docs/03 FR-VLT-02): ``page`` / ``page_size``, default 50, max 200."""

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class PageParams(BaseModel):
    """Query parameters; use as ``Annotated[PageParams, Query()]``."""

    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


PageQuery = Annotated[PageParams, Query()]


class ResultPage[T](BaseModel):
    """One page of results plus what a client needs to navigate."""

    items: list[T]
    page: int
    page_size: int
    total: int

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total
