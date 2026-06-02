FROM python:3.14

WORKDIR /app

COPY shared/ shared/
COPY services/trade-action-service/ .

EXPOSE 8008

RUN pip install -r requirements.txt

CMD ["python", "-m", "app.main"]
