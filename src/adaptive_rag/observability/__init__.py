"""Structured retrieval traces with a replaceable sink interface."""

from .traces import JsonlTraceSink, RetrievalTrace, TraceSink, make_trace

__all__ = ["JsonlTraceSink", "RetrievalTrace", "TraceSink", "make_trace"]
