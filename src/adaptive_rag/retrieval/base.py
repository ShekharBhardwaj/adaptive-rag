"""Independent baselines implement this interface; requests contain no answer labels."""

from typing import Protocol

from .models import RetrievalRequest, RetrievalResult


class Retriever(Protocol):
    def retrieve(self, request: RetrievalRequest) -> RetrievalResult: ...
