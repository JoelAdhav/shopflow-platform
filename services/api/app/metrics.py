"""Prometheus metrics for the api.

Counter   = number that only goes up (requests served).
Histogram = buckets of observed values (latency), used later for p95.
"""

import time

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests served", ["method", "path", "status"]
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.5, 5.0),
)
ORDERS_CREATED = Counter("orders_created_total", "Orders accepted by the api")
ENQUEUE_FAILURES = Counter(
    "orders_enqueue_failures_total", "Orders saved but not pushed to Redis"
)

# Paths we do not measure: probes and scrapes would drown real traffic.
_SKIP = {"/metrics", "/healthz", "/readyz"}


async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        # Use the route template (/products/{product_id}), not the real URL.
        # Real URLs would create one time series per id: "label cardinality" blow-up.
        route = request.scope.get("route")
        path = route.path if route else "unmatched"
        if path not in _SKIP:
            HTTP_REQUESTS.labels(request.method, path, str(status)).inc()
            HTTP_DURATION.labels(request.method, path).observe(time.perf_counter() - start)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
