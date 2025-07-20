FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PDF processing and image handling
RUN apt-get update && apt-get install -y \
    curl \
    libmagic1 \
    libmagic-dev \
    libmupdf-dev \
    mupdf-tools \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    libffi-dev \
    libcairo2-dev \
    libpango1.0-dev \
    python3-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create storage directories
RUN mkdir -p /app/storage/documents \
    && mkdir -p /app/storage/artifacts \
    && mkdir -p /app/storage/images

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY mcp-server.py .

# Set environment variables
ENV MCP_SERVER_HOST=0.0.0.0
ENV MCP_SERVER_PORT=8000
ENV STORAGE_PATH=/app/storage

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "mcp-server.py"]
