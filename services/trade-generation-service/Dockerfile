FROM python:3.14

WORKDIR /app

COPY shared/ shared/
COPY services/trade-generation-service/ .

EXPOSE 8007

RUN pip install -r requirements.txt

CMD ["python", "-m", "app.main"]
