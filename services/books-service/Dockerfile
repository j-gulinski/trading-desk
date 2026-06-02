FROM python:3.14

WORKDIR /app

COPY shared/ shared/
COPY services/books-service/ .

EXPOSE 8004

RUN pip install -r requirements.txt

CMD ["python", "-m", "app.main"]
