FROM python:3.14-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ARG SERVICE
COPY libs/ libs/
COPY services/${SERVICE}/ services/${SERVICE}/
RUN pip install --no-cache-dir --no-deps \
      libs/desk-pricing libs/desk-runtime libs/desk-domain services/${SERVICE}

ENV SERVICE=${SERVICE}
CMD ["sh", "-c", "exec \"$SERVICE\""]
