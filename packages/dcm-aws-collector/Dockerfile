FROM python:3.12-slim AS builder
WORKDIR /app
COPY packages/dcm-commons ./packages/dcm-commons
COPY packages/dcm-aws-collector ./packages/dcm-aws-collector
WORKDIR /app/packages/dcm-aws-collector
RUN pip install --no-cache-dir uv && uv pip install --system --no-cache .

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN useradd -r -u 1001 dcmcollector
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin/dcm-aws-collector /usr/local/bin/
COPY --from=builder /app/packages/dcm-aws-collector/aws_collector ./aws_collector/
COPY --from=builder /app/packages/dcm-commons/dcm_commons ./dcm_commons/
USER dcmcollector
CMD ["dcm-aws-collector"]
