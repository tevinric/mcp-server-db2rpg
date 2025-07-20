#!/bin/bash

# Environment Variables for DB2/RPG MCP Client (Azure OpenAI Integration)
# Run this script with: source env_var_init_client.sh

echo "🔧 Setting up DB2/RPG MCP Client Environment Variables"

# Azure OpenAI Configuration (REQUIRED)
# Replace these with your actual Azure OpenAI credentials
export AZURE_OPENAI_API_KEY="your-azure-openai-api-key-here"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o"
export AZURE_OPENAI_API_VERSION="2024-02-01"

# MCP Server Connection
export MCP_SERVER_URL="http://localhost:8000"
export MCP_TIMEOUT="60"  # seconds

# Client Configuration
export MAX_TOKENS="128000"  # GPT-4o context window
export MAX_RESPONSE_TOKENS="4000"
export TEMPERATURE="0.1"  # Lower for more deterministic code generation
export TOP_P="0.9"

# Code Generation Settings
export DEFAULT_CODE_TYPE="sql"
export INCLUDE_COMMENTS="true"
export CODE_STYLE="company_standards"
export REVIEW_LEVEL="detailed"
export EXPLANATION_LEVEL="intermediate"

# File Upload Settings
export AUTO_PROCESS_UPLOADS="true"
export DEFAULT_DOCUMENT_TYPE="reference"

# Artifact Settings
export ARTIFACT_AUTO_SAVE="true"
export ARTIFACT_INCLUDE_DOCS="true"

# Performance Settings
export REQUEST_TIMEOUT="120"  # seconds
export MAX_RETRIES="3"
export RETRY_DELAY="2"  # seconds

# Logging for Client
export CLIENT_LOG_LEVEL="INFO"
export CLIENT_LOG_FILE="./logs/mcp-client.log"

# Optional: Proxy Settings (if behind corporate firewall)
# export HTTP_PROXY="http://proxy.company.com:8080"
# export HTTPS_PROXY="http://proxy.company.com:8080"
# export NO_PROXY="localhost,127.0.0.1"

# Optional: Additional OpenAI Settings
# export OPENAI_ORG_ID="your-organization-id"
# export OPENAI_PROJECT_ID="your-project-id"

# Create logs directory if it doesn't exist
mkdir -p "./logs"

echo "✅ Client environment variables set:"

# Check if Azure OpenAI credentials are set properly
if [[ "$AZURE_OPENAI_API_KEY" == "your-azure-openai-api-key-here" ]]; then
    echo "❌ AZURE_OPENAI_API_KEY: Not configured (using placeholder)"
    echo "   Please update with your actual API key"
else
    echo "✅ AZURE_OPENAI_API_KEY: Configured"
fi

if [[ "$AZURE_OPENAI_ENDPOINT" == "https://your-resource.openai.azure.com/" ]]; then
    echo "❌ AZURE_OPENAI_ENDPOINT: Not configured (using placeholder)"
    echo "   Please update with your actual endpoint"
else
    echo "✅ AZURE_OPENAI_ENDPOINT: $AZURE_OPENAI_ENDPOINT"
fi

echo "✅ AZURE_OPENAI_DEPLOYMENT_NAME: $AZURE_OPENAI_DEPLOYMENT_NAME"
echo "✅ AZURE_OPENAI_API_VERSION: $AZURE_OPENAI_API_VERSION"
echo "✅ MCP_SERVER_URL: $MCP_SERVER_URL"
echo "✅ MAX_TOKENS: $MAX_TOKENS"

echo ""
echo "🔧 Configuration Settings:"
echo "   - Temperature: $TEMPERATURE (lower = more deterministic)"
echo "   - Max Response Tokens: $MAX_RESPONSE_TOKENS"
echo "   - Default Code Type: $DEFAULT_CODE_TYPE"
echo "   - Review Level: $REVIEW_LEVEL"
echo "   - Include Comments: $INCLUDE_COMMENTS"

echo ""
if [[ "$AZURE_OPENAI_API_KEY" == "your-azure-openai-api-key-here" ]] || [[ "$AZURE_OPENAI_ENDPOINT" == "https://your-resource.openai.azure.com/" ]]; then
    echo "⚠️  IMPORTANT: Update Azure OpenAI credentials before running client!"
    echo ""
    echo "   1. Get your credentials from Azure Portal"
    echo "   2. Edit this script and replace placeholders:"
    echo "      - AZURE_OPENAI_API_KEY"
    echo "      - AZURE_OPENAI_ENDPOINT"
    echo "   3. Re-run: source env_var_init_client.sh"
    echo ""
    echo "   Or set them directly:"
    echo "   export AZURE_OPENAI_API_KEY='your-actual-key'"
    echo "   export AZURE_OPENAI_ENDPOINT='https://your-actual-resource.openai.azure.com/'"
else
    echo "🚀 Ready to run client with: python client.py"
    echo "   Interactive mode: python client.py interactive"
fi
