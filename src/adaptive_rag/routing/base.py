"""Router boundary contains no evidence, benchmark annotations, or retrieval tools."""

from typing import Protocol

from .models import RoutingRequest, RoutingResult


class Router(Protocol):
    def route(self, request: RoutingRequest) -> RoutingResult: ...
