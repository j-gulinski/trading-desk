FROM python:3.14

WORKDIR /app

COPY shared.py .
COPY market-data-service/ .

EXPOSE 8001

RUN pip install -r requirements.txt

CMD ["python", "app.py"]