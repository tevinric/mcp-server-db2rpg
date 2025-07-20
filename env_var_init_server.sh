#!/bin/bash

# Environment Variables for DB2/RPG MCP Server
# Run this script with: source env_var_init_server.sh

echo "🔧 Setting up DB2/RPG MCP Server Environment Variables"

# MCP Server Configuration
export MCP_SERVER_HOST="0.0.0.0"
export MCP_SERVER_PORT="8000"
export MCP_SERVER_URL="http://localhost:8000"

# Storage Configuration
export STORAGE_PATH="./storage"
export DOCUMENTS_PATH="./storage/documents"
export ARTIFACTS_PATH="./storage/artifacts"
export IMAGES_PATH="./storage/images"

# File Upload Limits
export MAX_FILE_SIZE="52428800"  # 50MB in bytes
export ALLOWED_FILE_TYPES="pdf,md,markdown"

# Document Processing Configuration
export PDF_MAX_PAGES="1000"
export IMAGE_MAX_SIZE="4096x4096"
export TEXT_CHUNK_SIZE="10000"

# Performance Configuration
export MAX_CONCURRENT_UPLOADS="5"
export DOCUMENT_CACHE_SIZE="100"
export ARTIFACT_RETENTION_DAYS="30"

# Logging Configuration
export LOG_LEVEL="INFO"
export LOG_FILE="./logs/mcp-server.log"

# Security Configuration (Optional)
export ENABLE_CORS="true"
export ALLOWED_ORIGINS="http://localhost:3000,http://localhost:8080"

# Tool Configuration
export MAX_TOOL_CALLS="10"
export TOOL_TIMEOUT="30"  # seconds

# Code Generation Limits
export MAX_CODE_LENGTH="50000"  # characters
export MAX_ARTIFACT_SIZE="100000"  # characters

# Database Configuration (if using external DB)
# export DB_URL="postgresql://user:password@localhost:5432/mcp_db"
# export DB_POOL_SIZE="10"

# Redis Configuration (if using Redis for caching)
# export REDIS_URL="redis://localhost:6379"
# export REDIS_TTL="3600"  # 1 hour

# Create required directories
mkdir -p "./storage/documents"
mkdir -p "./storage/artifacts" 
mkdir -p "./storage/images"
mkdir -p "./logs"

echo "✅ Server environment variables set:"
echo "   - MCP_SERVER_HOST: $MCP_SERVER_HOST"
echo "   - MCP_SERVER_PORT: $MCP_SERVER_PORT"
echo "   - MCP_SERVER_URL: $MCP_SERVER_URL"
echo "   - STORAGE_PATH: $STORAGE_PATH"
echo "   - MAX_FILE_SIZE: $MAX_FILE_SIZE bytes"
echo "   - LOG_LEVEL: $LOG_LEVEL"

echo ""
echo "📁 Created directories:"
echo "   - ./storage/documents (for uploaded files)"
echo "   - ./storage/artifacts (for generated code)"
echo "   - ./storage/images (for extracted images)"
echo "   - ./logs (for server logs)"

echo ""
echo "🚀 Ready to start server with: python mcp-server.py"
