FROM python:3.14

WORKDIR /app

COPY pricing-service/ .
COPY shared.py .

EXPOSE 8002

RUN pip install -r requirements.txt

CMD ["python", "app.py"]