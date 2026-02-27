FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy dependencies first
COPY requirements.txt .
RUN apt-get update && apt-get install -y firejail curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

# Copy Architecture Layers
COPY core /app/core
COPY agents /app/agents
COPY workflows /app/workflows
COPY lab /app/lab
COPY start.sh /app/start.sh

# Permission & Execution
RUN chmod +x /app/start.sh
CMD ["/app/start.sh"]
