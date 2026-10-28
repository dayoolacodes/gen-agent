FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY tools ./tools
ENV PYTHONUNBUFFERED=1
# Cloud Run sets PORT (8080); tools/server.py reads it.
CMD ["python", "-m", "tools.server"]
