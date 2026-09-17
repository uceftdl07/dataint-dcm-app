"""DCM Backend API — FastAPI application entry point.

The database connection is created during the lifespan startup phase and attached
to ``app.state.db_pool`` so that route handlers can access it through the
``get_db`` FastAPI dependency without relying on module-level globals.

Reads from Databricks SQL Warehouse (Unity Catalog) — Lakebase PostgreSQL removed.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import (
    access_requests,
    activities,
    admin_access_requests,
    admin_alert_rules,
    admin_audit,
    admin_bundle,
    admin_channels,
    admin_collectors,
    admin_embedded_dashboards,
    admin_entra_search,
    admin_kpi_config,
    admin_lz,
    admin_maintenance,
    admin_retention,
    admin_users,
    auth,
    chat,
    clusters,
    compute_metrics,
    costs,
    dashboard,
    datafactory,
    databricks,
    data_product_usage,
    databases,
    governance,
    health,
    lakeflow,
    monitoring_reports,
    notification_preferences,
    pipelines,
    projects,
    security,
    sqs_to_raw_in,
    uc_usage,
    unity_catalog,
    users,
)
from .api.services.compute_metrics_filters import ColumnFilterError
from .config import CORSSettings, Settings
from .db.connection import DatabricksWarehousePool

__all__ = ["app", "start"]

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open warehouse connection on startup; close on shutdown.

    In development, a connection failure is non-fatal: ``app.state.db_pool`` is
    set to ``None`` so /docs and mocked tests still work.
    """
    settings: Settings = app.state.settings  # type: ignore[attr-defined]
    logger.info(
        "Databricks config at startup: host=%s warehouse_id=%s catalog=%s schema=%s "
        "entra_client_id=%s entra_tenant_id=%s auth_disabled=%s "
        "spn_client_id=%s spn_secret=%s spn_secret_arn=%s token=%s",
        settings.databricks_host or "(empty)",
        settings.databricks_warehouse_id or "(empty)",
        settings.databricks_catalog,
        settings.databricks_schema,
        settings.entra_client_id or "(empty)",
        settings.entra_tenant_id or "(empty)",
        settings.auth_disabled,
        "set" if settings.databricks_spn_client_id else "MISSING",
        "set" if settings.databricks_spn_client_secret else "MISSING",
        "set" if settings.databricks_spn_client_secret_arn else "MISSING",
        "set" if settings.databricks_token else "unset",
    )
    logger.info(
        "Chat config at startup: provider=%s genie_space_id=%s genie_api_base_url=%s",
        settings.chat_provider or "(empty)",
        "set" if settings.genie_space_id.strip() else "EMPTY",
        "set" if settings.genie_api_base_url.strip() else "default",
    )

    pool = DatabricksWarehousePool(settings)
    app.state.db_pool = None
    try:
        await pool.connect()
        app.state.db_pool = pool
        logger.info(
            "Databricks Warehouse pool ready (size=%s)",
            pool.pool_size,
            extra={
                "host": settings.databricks_host,
                "catalog": settings.databricks_catalog,
                "schema": settings.databricks_schema,
                "http_path": settings.resolved_http_path,
            },
        )
    except Exception as exc:
        # Do not block HTTP startup — /health/live must respond while DB is misconfigured.
        logger.exception(
            "Could not connect to Databricks at startup — API up, data routes return 503. "
            "Check DCM_DATABRICKS_HOST, DCM_DATABRICKS_WAREHOUSE_ID, "
            "DCM_DATABRICKS_SPN_CLIENT_ID, DCM_DATABRICKS_SPN_CLIENT_SECRET, "
            "DCM_DATABRICKS_SPN_CLIENT_SECRET_ARN. Error type=%s message=%s",
            type(exc).__name__,
            exc,
        )
    try:
        yield
    finally:
        if app.state.db_pool is not None:
            await pool.disconnect()
            logger.info("Databricks connection closed")


def _build_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_secrets_manager()
    settings.log_runtime_env_diagnostics()
    settings.log_databricks_diagnostics()

    application = FastAPI(
        title="Data Connect Monitoring API",
        version="0.1.0",
        description=(
            "DCM Core Backend — monitoring metrics for Azure and AWS data services. "
            "Reads from Databricks SQL Warehouse (Unity Catalog)."
        ),
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    application.state.settings = settings

    @application.exception_handler(ColumnFilterError)
    async def column_filter_error_handler(
        request: Request, exc: ColumnFilterError
    ) -> JSONResponse:
        """A rejected ``column_filter`` is a 422, with the accepted keys in the detail.

        Registered here rather than caught per route: the eleven list services and the
        two ``filter-options`` routes raise it, and the alternative — a ``try`` in each
        handler — is exactly how a refused filter ends up answered as an empty table.
        ``detail`` is the shape FastAPI already uses for a query-string error, so the
        frontend has one error path, not two.
        """
        # The literal rather than ``status.HTTP_422_…``: the constant was renamed
        # between Starlette versions and the old spelling now warns on import use.
        return JSONResponse(status_code=422, content={"detail": exc.detail})

    cors_settings = CORSSettings()
    allowed_origins = cors_settings.get_allowed_origins()

    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def log_requests(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/v1/auth"):
            auth_header = request.headers.get("authorization", "")
            has_bearer = auth_header.lower().startswith("bearer ") and len(auth_header) > 7
            logger.info(
                "[DCM_AUTH] incoming method=%s path=%s has_bearer=%s bearer_len=%s",
                request.method,
                path,
                has_bearer,
                len(auth_header),
            )
            response = await call_next(request)
            logger.info(
                "[DCM_AUTH] completed method=%s path=%s status=%s",
                request.method,
                path,
                response.status_code,
            )
            return response

        origin = request.headers.get("origin", "-")
        logger.debug("Request %s %s origin=%s", request.method, path, origin)
        return await call_next(request)

    application.include_router(health.router, prefix="/api/v1", tags=["health"])
    application.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    application.include_router(access_requests.router, prefix="/api/v1", tags=["access-requests"])
    application.include_router(projects.router, prefix="/api/v1", tags=["projects"])
    application.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
    application.include_router(pipelines.router, prefix="/api/v1/pipelines", tags=["pipelines"])
    application.include_router(activities.router, prefix="/api/v1", tags=["activities"])
    application.include_router(clusters.router, prefix="/api/v1/clusters", tags=["compute"])
    application.include_router(databricks.router, prefix="/api/v1/databricks", tags=["databricks"])
    application.include_router(lakeflow.router, prefix="/api/v1/lakeflow", tags=["lakeflow"])
    application.include_router(
        compute_metrics.router,
        prefix="/api/v1/databricks/compute",
        tags=["compute-metrics"],
    )
    application.include_router(datafactory.router, prefix="/api/v1/datafactory", tags=["datafactory"])
    application.include_router(costs.router, prefix="/api/v1/costs", tags=["costs"])
    application.include_router(
        data_product_usage.router,
        prefix="/api/v1/data-product-usage",
        tags=["data-product-usage"],
    )
    application.include_router(databases.router, prefix="/api/v1/databases", tags=["databases"])
    application.include_router(security.router, prefix="/api/v1/security", tags=["security"])
    application.include_router(users.router, prefix="/api/v1", tags=["users"])
    application.include_router(
        notification_preferences.router,
        prefix="/api/v1",
        tags=["notification-preferences"],
    )
    application.include_router(admin_users.router, prefix="/api/v1", tags=["admin-users"])
    application.include_router(admin_bundle.router, prefix="/api/v1", tags=["admin-bundle"])
    application.include_router(
        admin_access_requests.router,
        prefix="/api/v1",
        tags=["admin-access-requests"],
    )
    application.include_router(admin_entra_search.router, prefix="/api/v1", tags=["admin-entra"])
    application.include_router(admin_lz.router, prefix="/api/v1", tags=["admin-landing-zones"])
    application.include_router(
        admin_channels.router,
        prefix="/api/v1",
        tags=["admin-notification-channels"],
    )
    application.include_router(
        admin_alert_rules.router,
        prefix="/api/v1",
        tags=["admin-alert-rules"],
    )
    application.include_router(
        admin_collectors.router,
        prefix="/api/v1",
        tags=["admin-collectors"],
    )
    application.include_router(
        admin_kpi_config.router,
        prefix="/api/v1",
        tags=["admin-kpi-config"],
    )
    application.include_router(
        admin_retention.router,
        prefix="/api/v1",
        tags=["admin-retention"],
    )
    application.include_router(
        admin_maintenance.router,
        prefix="/api/v1",
        tags=["admin-maintenance"],
    )
    application.include_router(
        admin_embedded_dashboards.router,
        prefix="/api/v1",
        tags=["admin-embedded-dashboards"],
    )
    application.include_router(admin_audit.router, prefix="/api/v1", tags=["admin-audit"])
    application.include_router(governance.router, prefix="/api/v1", tags=["standard-checks"])
    application.include_router(
        monitoring_reports.router,
        prefix="/api/v1/monitoring-reports",
        tags=["monitoring-reports"],
    )
    application.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    application.include_router(
        unity_catalog.router,
        prefix="/api/v1/unity-catalog",
        tags=["unity-catalog"],
    )
    application.include_router(
        uc_usage.router,
        prefix="/api/v1/uc-usage",
        tags=["uc-usage"],
    )
    application.include_router(sqs_to_raw_in.router, prefix="/api/v1/ingest", tags=["ingest"])

    return application


app = _build_app()


def start() -> None:
    """Entry point for ``dcm-backend`` console script (production)."""
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=False)
