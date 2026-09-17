# Build context is the repo root: `dcm-commons` is a path dependency of this
# package (`tool.uv.sources`), so it has to be inside the context for uv to
# resolve it. Same layout as the other packages that depend on it.
FROM python:3.12-slim AS builder
WORKDIR /app
COPY packages/dcm-commons ./packages/dcm-commons
COPY packages/dcm-backend ./packages/dcm-backend
WORKDIR /app/packages/dcm-backend
RUN pip install --no-cache-dir uv && uv pip install --system --no-cache .

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -r -u 1001 dcmapi
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/
RUN mkdir -p ./certs
RUN openssl req -x509 -newkey rsa:4096 -keyout certs/key.pem -out certs/cert.pem -sha256 -days 3650 -nodes -subj "/C=FR/ST=IdF/L=Paris/O=TotalEnergies/OU=DGT/CN=api.dcm.private.alzp.tgscloud.net"
COPY --from=builder /app/packages/dcm-backend/app ./app/
# `dcm-commons` is installed editable, so the link points at a builder-only path.
# WORKDIR is /app, so shipping the sources here is what makes `import dcm_commons`
# resolve at runtime.
COPY --from=builder /app/packages/dcm-commons/dcm_commons ./dcm_commons/
RUN chown -R dcmapi:dcmapi /app ./certs && chmod -R 700 ./certs
USER dcmapi
EXPOSE 8443
HEALTHCHECK --interval=30s --timeout=5s CMD ["python", "-c", "import httpx; httpx.get('https://localhost:8443/api/v1/health/live', verify=False).raise_for_status()"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8443", "--ssl-keyfile", "./certs/key.pem", "--ssl-certfile", "./certs/cert.pem"]
