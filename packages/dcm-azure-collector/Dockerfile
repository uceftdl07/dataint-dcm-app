FROM python:3.12-slim AS builder
WORKDIR /app
COPY packages/dcm-commons ./packages/dcm-commons
COPY packages/dcm-azure-collector ./packages/dcm-azure-collector
# Non-editable installs: editable .pth points at builder paths missing in the runtime stage.
RUN pip install --no-cache-dir ./packages/dcm-commons ./packages/dcm-azure-collector

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN useradd -r -u 1001 dcmcollector
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin/dcm-azure-collector /usr/local/bin/
ENV PYTHONUNBUFFERED=1
USER dcmcollector
HEALTHCHECK --interval=60s --timeout=10s CMD ["python", "-c", "import azure_collector, dcm_commons; print('ok')"]
CMD ["dcm-azure-collector"]
