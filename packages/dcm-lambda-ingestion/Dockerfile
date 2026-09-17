# Build Lambda artifacts for dcm-ingestion-api (PackageType=Zip, arch x86_64).
#
# Targets:
#   layer-export    → python/… (deps + dcm_commons)
#   function-export → lambda_ingestion/ (app code only)
#   runtime         → full container image (future PackageType=Image)

FROM public.ecr.aws/lambda/python:3.12 AS builder

COPY packages/dcm-commons /tmp/packages/dcm-commons
COPY packages/dcm-lambda-ingestion /tmp/packages/dcm-lambda-ingestion

# Install into layer path; copy dcm_commons source explicitly (no editable .pth).
RUN mkdir -p /opt/layer/python \
    && pip install --no-cache-dir --target /opt/layer/python \
         /tmp/packages/dcm-commons /tmp/packages/dcm-lambda-ingestion \
    && rm -f /opt/layer/python/_editable_*.pth \
    && python -c "\
import pathlib; \
root = pathlib.Path('/opt/layer/python'); \
[p.unlink() for p in root.glob('*.pth') if p.is_file() and '/tmp/packages' in p.read_text(encoding='utf-8', errors='ignore')] \
" \
    && cp -a /tmp/packages/dcm-commons/dcm_commons /opt/layer/python/dcm_commons \
    && test -f /opt/layer/python/dcm_commons/__init__.py \
    && rm -rf /opt/layer/python/lambda_ingestion \
           /opt/layer/python/lambda_ingestion-*.dist-info \
           /opt/layer/python/dcm_lambda_ingestion-*.dist-info \
    && PYTHONPATH=/opt/layer/python python -c \
         "import dcm_commons.models.payload; print('layer imports ok')"

FROM scratch AS layer-export
COPY --from=builder /opt/layer /

FROM scratch AS function-export
COPY --from=builder /tmp/packages/dcm-lambda-ingestion/lambda_ingestion /lambda_ingestion

FROM public.ecr.aws/lambda/python:3.12 AS runtime
COPY packages/dcm-commons /tmp/packages/dcm-commons
COPY packages/dcm-lambda-ingestion /tmp/packages/dcm-lambda-ingestion
RUN pip install --no-cache-dir /tmp/packages/dcm-commons /tmp/packages/dcm-lambda-ingestion \
    && rm -f /var/lang/lib/python3.12/site-packages/_editable_*.pth \
    && python -c "import dcm_commons, lambda_ingestion.handler; print('imports ok')"
CMD ["lambda_ingestion.handler.handler"]
