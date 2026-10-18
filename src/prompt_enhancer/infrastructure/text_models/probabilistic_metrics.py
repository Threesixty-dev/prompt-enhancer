"""Compatibility module for the versioned session-analysis workflow."""
import sys
from ...workflows import session_analysis as _implementation

# Preserve existing monkeypatch/injection seams as well as import identities.
sys.modules[__name__] = _implementation
