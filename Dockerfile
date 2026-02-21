FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render.com PORT environment variable kullanır
EXPOSE 10000

CMD ["python", "monitor.py"]
