FROM python:3.12-slim AS builder
WORKDIR /app
COPY dcm-aws-collector/pyproject.toml ./pyproject.toml
COPY dcm-aws-collector/README.md ./README.md
COPY dcm-commons /dcm-commons

RUN pip install --no-cache-dir uv && uv pip install --system --no-cache --no-editable .

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN useradd -r -u 1001 dcmcollector
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin/dcm-aws-collector /usr/local/bin/
COPY --chown=dcmcollector:dcmcollector dcm-aws-collector/aws_collector aws_collector
ENV PYTHONPATH=/app
USER dcmcollector
CMD ["dcm-aws-collector"]
