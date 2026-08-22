FROM python:3.14-slim AS deps
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.14-slim
ARG SERVICE_DIR
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY --from=deps /opt/venv /opt/venv
COPY alembic.ini ./
COPY shared/ shared/
COPY db/ db/
COPY ${SERVICE_DIR}/ ./
CMD ["python", "-m", "app.main"]
