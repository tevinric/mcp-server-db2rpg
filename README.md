# DB2/RPG Code Generation MCP Server

A specialized Model Control Protocol (MCP) server for IBM DB2 and RPG code generation, review, and documentation. This server allows LLMs to generate, review, and explain code based on uploaded coding standards and reference documents.

## Features

- **Document Upload**: Support for PDF and Markdown files containing coding standards
- **Code Generation**: Generate DB2/SQL and RPG code based on requirements
- **Code Review**: Review existing code against uploaded standards
- **Code Explanation**: Explain code functionality with reference to documentation
- **Image Processing**: Extract and analyze images from PDF documents using PyMuPDF
- **Artifact Creation**: Generate large code artifacts with proper structure
- **Context Management**: Stay within 128K token limits with intelligent truncation
- **Azure OpenAI Integration**: Full integration with GPT-4o for code assistance

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Application                       │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ Azure OpenAI    │    │ Python Client   │                │
│  │ GPT-4o         │◄──►│ Application     │                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────────────────┬───────────────────────────┘
                                  │ HTTP/MCP Protocol
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│              MCP Server (FastAPI)                          │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ Code Generation │    │ Document        │                │
│  │ Tools           │    │ Processing      │                │
│  │ • generate_code │    │ • PDF extraction│                │
│  │ • review_code   │    │ • Image analysis│                │
│  │ • explain_code  │    │ • Markdown      │                │
│  │ • create_artifact│   │ • Text search   │                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────────────────┬───────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│                 File Storage                                │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ Documents       │    │ Generated       │                │
│  │ • Standards     │    │ Artifacts       │                │
│  │ • Procedures    │    │ • Modules       │                │
│  │ • Best Practices│    │ • Procedures    │                │
│  │ • References    │    │ • Programs      │                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Environment Setup

```bash
# Set up environment variables
source env_var_init_server.sh  # For server
source env_var_init_client.sh  # For client

# Install dependencies
pip install -r requirements.txt
```

### 2. Start the MCP Server

```bash
# Run locally
python mcp-server.py

# Or using Docker
docker-compose up -d
```

### 3. Upload Reference Documents

```bash
# Upload coding standards (PDF/Markdown)
curl -X POST -F "file=@coding_standards.pdf" http://localhost:8000/upload
curl -X POST -F "file=@rpg_best_practices.md" http://localhost:8000/upload
```

### 4. Run the Client

```bash
# Interactive mode
python client.py interactive

# Example mode
python client.py
```

## Available Tools

### 1. `upload_document`
Process uploaded PDF or Markdown documents containing coding standards.

**Parameters:**
- `filename`: Name of the uploaded file
- `document_type`: Type (standards/procedures/best_practices/reference/examples)
- `description`: Brief description of the document

### 2. `search_references`
Search through uploaded documents for specific topics or patterns.

**Parameters:**
- `query`: Search query
- `document_type`: Filter by document type (default: "all")
- `max_results`: Maximum results to return (default: 5)

### 3. `extract_code_examples`
Extract code examples and patterns from reference documents.

**Parameters:**
- `code_type`: Type of code (all/sql/db2/rpg/procedure)
- `topic`: Specific topic to find examples for

### 4. `generate_code`
Generate new code based on requirements and reference standards.

**Parameters:**
- `requirements`: Detailed requirements for the code
- `code_type`: Type of code (sql/db2/rpg/procedure)
- `style_guide`: Style guide to follow (default: "company_standards")
- `include_comments`: Include detailed comments (default: true)

### 5. `review_code`
Review existing code against uploaded standards and best practices.

**Parameters:**
- `code`: Code to be reviewed
- `code_type`: Type of code being reviewed
- `review_level`: Level of detail (basic/detailed/comprehensive)

### 6. `explain_code`
Explain code functionality using reference documentation.

**Parameters:**
- `code`: Code to be explained
- `explanation_level`: Detail level (beginner/intermediate/advanced)
- `include_references`: Include documentation references (default: true)

### 7. `create_artifact`
Create large code artifacts with proper structure.

**Parameters:**
- `artifact_type`: Type (module/procedure/package/complete_program)
- `specifications`: Detailed specifications
- `include_documentation`: Include comprehensive docs (default: true)

### 8. `list_documents`
List all uploaded reference documents with metadata.

**Parameters:**
- `document_type`: Filter by document type (default: "all")

## Usage Examples

### Code Generation

```python
# Generate SQL code
requirements = "Create a stored procedure to calculate customer order totals with tax"
response = await code_client.generate_code(requirements, "sql")
```

### Code Review

```python
# Review RPG code
code = """
DCL-S customerID PACKED(7:0);
EXEC SQL SELECT customer_id INTO :customerID FROM customers;
"""
response = await code_client.review_code(code, "rpg")
```

### Document Upload and Processing

```python
# Upload and process a standards document
await mcp_client.upload_document("db2_standards.pdf")
await mcp_client.call_tool("upload_document", {
    "filename": "db2_standards.pdf",
    "document_type": "standards",
    "description": "Company DB2 coding standards"
})
```

## Interactive Commands

When running `python client.py interactive`:

- `upload <file_path>` - Upload reference document
- `generate <type> <requirements>` - Generate code
- `review <type> <code>` - Review code (enter code, end with '###')
- `explain <code>` - Explain code (enter code, end with '###')
- `artifact <type> <specs>` - Create large artifact
- `docs` - List uploaded documents
- `artifacts` - List generated artifacts
- `help` - Show help
- `quit` - Exit

## Document Types

### Supported Formats
- **PDF**: Extracted using PyMuPDF with image analysis
- **Markdown**: Direct text processing

### Document Categories
- **standards**: Coding standards and conventions
- **procedures**: Development procedures and workflows
- **best_practices**: Best practice guidelines
- **reference**: Technical reference materials
- **examples**: Code examples and templates

## Context Window Management

The system automatically manages the 128K token context window:

1. **Content Truncation**: Long documents are intelligently truncated
2. **Message Pruning**: Older conversation messages are removed when needed
3. **Artifact Generation**: Large code outputs are saved as artifacts
4. **Tool Result Limiting**: Tool outputs are truncated to manageable sizes

## Environment Variables

### Server Variables
```bash
export MCP_SERVER_HOST="0.0.0.0"
export MCP_SERVER_PORT="8000"
export STORAGE_PATH="./storage"
```

### Client Variables
```bash
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o"
export AZURE_OPENAI_API_VERSION="2024-02-01"
export MCP_SERVER_URL="http://localhost:8000"
```

## API Endpoints

### MCP Protocol
- `POST /mcp` - Main MCP protocol endpoint

### File Management
- `POST /upload` - Upload documents
- `GET /documents` - List uploaded documents
- `GET /artifacts` - List generated artifacts

### Health Check
- `GET /health` - Server health status
- `GET /` - Server information

## Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f mcp-server

# Stop
docker-compose down
```

## Development

### Adding New Tools

1. Add tool definition in `list_tools()` function
2. Add implementation in `call_tool()` function
3. Update client if needed

### Extending Document Processing

1. Add new file type support in `DocumentProcessor`
2. Update upload validation
3. Add new analysis methods in `CodeAnalyzer`

## Troubleshooting

### Common Issues

1. **Server not starting**: Check environment variables and port availability
2. **Upload failures**: Verify file format and size (max 50MB)
3. **Azure OpenAI errors**: Check API key and endpoint configuration
4. **Context window exceeded**: Documents will be automatically truncated

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python mcp-server.py
```

## Security Considerations

- Store API keys securely using environment variables
- Validate all uploaded files for security
- Implement proper access controls for production use
- Regular security updates for dependencies

## Performance

- Document processing is optimized for speed
- Images are cached for repeated access
- Code analysis results are stored for quick retrieval
- Automatic cleanup of old artifacts

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Submit pull request

## License

This project is provided as-is for educational and development purposes.
