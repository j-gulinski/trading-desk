FROM python:3.14

WORKDIR /app

COPY shared/ shared/
COPY market-data-service/ .

EXPOSE 8001

RUN pip install -r requirements.txt

CMD ["python", "-m", "app.main"]