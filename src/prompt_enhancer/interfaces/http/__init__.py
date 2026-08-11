"""Narrow HTTP query interface for the local dashboard."""

from .task_routes import create_task_query_router
from .session_analysis_command_routes import create_session_analysis_command_router
from .session_analysis_routes import create_session_analysis_query_router
from .session_quality_aggregation_routes import (
    create_session_quality_aggregation_router,
)
from .project_quality_aggregation_routes import (
    create_project_quality_aggregation_router,
)
from .provider_compatibility_routes import create_provider_compatibility_router
from .research_routes import create_research_router
from .model_link_experiment_routes import create_model_link_experiment_router

__all__ = (
    "create_session_analysis_command_router",
    "create_session_analysis_query_router",
    "create_session_quality_aggregation_router",
    "create_project_quality_aggregation_router",
    "create_provider_compatibility_router",
    "create_research_router",
    "create_model_link_experiment_router",
    "create_task_query_router",
)
