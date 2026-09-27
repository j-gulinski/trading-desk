FROM python:3.14.7-slim
ARG TARGETARCH
ADD --chmod=755 https://github.com/hatoo/oha/releases/download/v1.16.0/oha-linux-${TARGETARCH} /usr/local/bin/oha
RUN apt-get update && apt-get install -y --no-install-recommends procps && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY benchmark/infra/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY libs/ libs/
COPY services/books-service/ services/books-service/
RUN pip install --no-cache-dir --no-deps \
      libs/desk-pricing libs/desk-runtime libs/desk-domain services/books-service
COPY alembic.ini ./
COPY db/ db/

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/bench
WORKDIR /bench
