#!/usr/bin/env python3
"""
Centralized configuration for PaperAtlas.

All configuration values can be overridden via environment variables.
"""

import os

# =============================================================================
# Relevance Thresholds
# =============================================================================

# Papers with scores >= this threshold are considered "highly relevant"
# Used for author ranking and filtering throughout the application
HIGHLY_RELEVANT_THRESHOLD = int(
    os.environ.get("PAPERATLAS_HIGHLY_RELEVANT_THRESHOLD", 85)
)

# =============================================================================
# Worker Configuration
# =============================================================================

# Number of parallel workers for author enrichment
AUTHOR_ENRICHMENT_WORKERS = int(
    os.environ.get("PAPERATLAS_AUTHOR_WORKERS", 30)
)

# Number of parallel workers for paper enrichment
PAPER_ENRICHMENT_WORKERS = int(
    os.environ.get("PAPERATLAS_PAPER_WORKERS", 30)
)

# =============================================================================
# Default Models
# =============================================================================

# Default model for author enrichment (biographical info lookup)
DEFAULT_AUTHOR_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "openai/gpt-5-mini"
)

# Default model for paper enrichment (abstract/details lookup)
DEFAULT_PAPER_MODEL = os.environ.get(
    "OPENROUTER_PAPER_MODEL", "anthropic/claude-sonnet-4.5"
)

# Default model for conference synthesis
DEFAULT_SYNTHESIS_MODEL = os.environ.get(
    "OPENROUTER_SYNTHESIS_MODEL", "anthropic/claude-sonnet-4.5"
)

# =============================================================================
# API Configuration
# =============================================================================

# Scholar Inbox API base URL
SCHOLAR_INBOX_API_BASE = os.environ.get(
    "PAPERATLAS_SCHOLAR_INBOX_API", "https://api.scholar-inbox.com/api"
)

# OpenRouter API configuration
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)

OPENROUTER_HTTP_REFERER = os.environ.get(
    "OPENROUTER_HTTP_REFERER", "https://github.com/aldro61/PaperAtlas"
)

OPENROUTER_APP_TITLE = os.environ.get(
    "OPENROUTER_APP_TITLE", "PaperAtlas"
)
