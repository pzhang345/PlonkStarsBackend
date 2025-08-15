# Use Python base image
FROM python:3.13-slim
# Set working directory in the container
WORKDIR /app

RUN apt-get update && apt-get install -y \
    pkg-config \
    default-libmysqlclient-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY ../requirements.txt /app/requirements.txt
RUN grep -v "psycopg2" requirements.txt > requirements_filtered.txt
RUN pip install --no-cache-dir -r requirements_filtered.txt

# Copy application code
COPY /app /app

# Expose Flask port
EXPOSE 5000

# Run the Flask app
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]