FROM python:3.11-slim

WORKDIR /app

# Install dependencies in a separate layer so they cache on rebuilds
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "run_pipeline.py"]
