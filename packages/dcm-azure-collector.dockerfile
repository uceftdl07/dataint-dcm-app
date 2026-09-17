FROM python:3.12-slim AS builder
WORKDIR /app
COPY dcm-azure-collector/pyproject.toml ./pyproject.toml
COPY dcm-azure-collector/README.md ./README.md
COPY dcm-commons /dcm-commons

RUN pip install --no-cache-dir uv && uv pip install --system --no-cache --no-editable .

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN useradd -r -u 1001 dcmcollector
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin/dcm-azure-collector /usr/local/bin/
COPY --chown=dcmcollector:dcmcollector dcm-azure-collector/azure_collector azure_collector
ENV PYTHONPATH=/app
USER dcmcollector
HEALTHCHECK --interval=60s --timeout=10s CMD ["python", "-c", "import azure_collector; print('ok')"]
CMD ["dcm-azure-collector"]
