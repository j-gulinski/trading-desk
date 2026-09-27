FROM python:3.14.7-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ARG SERVICE
COPY libs/ libs/
COPY services/${SERVICE}/ services/${SERVICE}/
RUN pip install --no-cache-dir --no-deps \
      libs/desk-pricing libs/desk-runtime libs/desk-domain services/${SERVICE}

ENV SERVICE=${SERVICE}
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=20s CMD \
  python -c "import os, urllib.request; from desk_runtime.config import SERVICE_PORTS; urllib.request.urlopen(f'http://127.0.0.1:{SERVICE_PORTS[os.environ[\"SERVICE\"]]}/health', timeout=3)"
CMD ["sh", "-c", "exec \"$SERVICE\""]
