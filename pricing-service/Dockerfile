FROM python:3.14

WORKDIR /app

COPY pricing-service/ .
COPY shared/ shared/

EXPOSE 8002

RUN pip install -r requirements.txt

CMD ["python", "-m", "app.main"]