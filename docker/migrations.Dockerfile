FROM python:3.14-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY libs/desk-runtime/ libs/desk-runtime/
COPY libs/desk-domain/ libs/desk-domain/
COPY libs/desk-pricing/ libs/desk-pricing/
RUN pip install --no-cache-dir --no-deps libs/desk-pricing libs/desk-runtime libs/desk-domain

COPY alembic.ini ./
COPY db/ db/

CMD ["alembic", "upgrade", "head"]
