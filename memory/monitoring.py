"""
Monitoring — Health check and metrics endpoints.

This module provides endpoints for monitoring the health and performance
of the KinnyCode Memory Server.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

# Create router for monitoring endpoints
router = APIRouter(tags=["monitoring"])

# Server start time for uptime calculation
_start_time: float = time.time()

# Simple in-memory metrics collector
_metrics: dict[str, Any] = {
    "requests_total": 0,
    "requests_by_endpoint": {},
    "errors_total": 0,
    "indexing_operations": 0,
    "search_operations": 0,
    "embedding_cache_hits": 0,
    "embedding_cache_misses": 0,
}


def track_request(endpoint: str, is_error: bool = False) -> None:
    """Track a request for metrics.
    
    Args:
        endpoint: The endpoint path.
        is_error: Whether the request resulted in an error.
    """
    _metrics["requests_total"] += 1
    
    if endpoint not in _metrics["requests_by_endpoint"]:
        _metrics["requests_by_endpoint"][endpoint] = 0
    _metrics["requests_by_endpoint"][endpoint] += 1
    
    if is_error:
        _metrics["errors_total"] += 1


def track_indexing() -> None:
    """Track an indexing operation."""
    _metrics["indexing_operations"] += 1


def track_search() -> None:
    """Track a search operation."""
    _metrics["search_operations"] += 1


def track_embedding_cache(hit: bool) -> None:
    """Track an embedding cache hit or miss.
    
    Args:
        hit: True if cache hit, False if miss.
    """
    if hit:
        _metrics["embedding_cache_hits"] += 1
    else:
        _metrics["embedding_cache_misses"] += 1


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint.
    
    Returns:
        Dictionary with health status and basic info.
    """
    uptime_seconds = time.time() - _start_time
    
    return {
        "status": "healthy",
        "version": "0.5.0",
        "uptime_seconds": round(uptime_seconds, 2),
        "uptime_human": _format_uptime(uptime_seconds),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics")
async def get_metrics() -> dict[str, Any]:
    """Prometheus-compatible metrics endpoint.
    
    Returns:
        Dictionary with server metrics.
    """
    uptime_seconds = time.time() - _start_time
    
    # Calculate cache hit rate
    total_cache_requests = (
        _metrics["embedding_cache_hits"] + _metrics["embedding_cache_misses"]
    )
    cache_hit_rate = (
        (_metrics["embedding_cache_hits"] / total_cache_requests * 100)
        if total_cache_requests > 0
        else 0.0
    )
    
    return {
        "uptime_seconds": round(uptime_seconds, 2),
        "requests": {
            "total": _metrics["requests_total"],
            "by_endpoint": _metrics["requests_by_endpoint"],
            "errors_total": _metrics["errors_total"],
        },
        "operations": {
            "indexing_total": _metrics["indexing_operations"],
            "search_total": _metrics["search_operations"],
        },
        "embedding_cache": {
            "hits": _metrics["embedding_cache_hits"],
            "misses": _metrics["embedding_cache_misses"],
            "hit_rate_percent": round(cache_hit_rate, 2),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def readiness_check() -> dict[str, Any]:
    """Readiness check endpoint for load balancers.
    
    Returns:
        Dictionary with readiness status.
    """
    return {
        "status": "ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _format_uptime(seconds: float) -> str:
    """Format uptime seconds into human-readable string.
    
    Args:
        seconds: Uptime in seconds.
        
    Returns:
        Human-readable uptime string.
    """
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    
    return " ".join(parts)
