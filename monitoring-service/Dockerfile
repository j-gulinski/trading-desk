FROM python:3.14

WORKDIR /app

COPY monitoring-service/ .
COPY shared/ shared/

EXPOSE 8003

RUN pip install -r requirements.txt

CMD ["python", "-m", "app.main"]