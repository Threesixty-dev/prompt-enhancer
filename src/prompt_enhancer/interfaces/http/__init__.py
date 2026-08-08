"""Narrow HTTP query interface for the local dashboard."""

from .task_routes import create_task_query_router

__all__ = ("create_task_query_router",)
