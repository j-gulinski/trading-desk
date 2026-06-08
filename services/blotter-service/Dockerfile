FROM python:3.14

WORKDIR /app

COPY shared/ shared/
COPY services/blotter-service/ .

EXPOSE 8006

RUN pip install -r requirements.txt

CMD ["python", "-m", "app.main"]
