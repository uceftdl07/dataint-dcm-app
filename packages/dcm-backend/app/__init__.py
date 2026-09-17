"""DCM Backend — FastAPI service exposing Lakebase metrics to the frontend.

Architecture:
    Lakebase PostgreSQL (replica, TLS)
          │
          └── asyncpg connection pool
                    │
                    └── FastAPI routes (health / dashboard / pipelines /
                                       clusters / costs / databases / security)
                              │
                              └── ECS Fargate (behind ALB + API Gateway + WAF)

Authentication is handled upstream by the API Gateway Lambda Authorizer
(Entra ID JWT validation).  FastAPI itself receives pre-validated requests
and does NOT re-validate tokens in the default configuration.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
