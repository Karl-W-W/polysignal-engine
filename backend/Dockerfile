FROM python:3.11-slim
WORKDIR /app
# Copy just the requirements first (for better caching)
COPY requirements.txt .
# Install ALL dependencies (Flask, Google, Requests, etc.)
RUN pip install --no-cache-dir -r requirements.txt
# Now copy the rest of the code
COPY . .
CMD ["python", "app.py"]
