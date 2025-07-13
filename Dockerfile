FROM python:3.13.5-alpine

WORKDIR /app

RUN apk add --no-cache ffmpeg

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "main.py"]