# Enhanced DB2/RPG Code Generation MCP Server

A specialized Model Control Protocol (MCP) server for IBM DB2 and RPG code generation, review, documentation, and **traditional-to-freeform RPG conversion**. This server allows LLMs to generate, review, explain, and convert code based on uploaded coding standards and reference documents.

## 🆕 New Features in v1.1

### RPG Traditional-to-Freeform Conversion
- **Automatic Analysis**: Analyze traditional RPG code structure and complexity
- **Intelligent Conversion**: Convert fixed-format RPG to modern free-form syntax
- **Standards Compliance**: Apply uploaded coding standards during conversion
- **Validation Tools**: Validate converted code against original functionality
- **Modernization Suggestions**: Get recommendations for improving legacy code

### Enhanced Document Processing
- **Section Extraction**: Retrieve specific sections from coding standards documents
- **Pattern Recognition**: Extract RPG-specific coding patterns and conventions
- **Conversion Guides**: Support for specialized RPG conversion documentation
- **Enhanced Code Detection**: Improved recognition of both traditional and free-form RPG

## Features

- **Document Upload**: Support for PDF and Markdown files containing coding standards
- **Code Generation**: Generate DB2/SQL and RPG code based on requirements
- **Code Review**: Review existing code against uploaded standards
- **Code Explanation**: Explain code functionality with reference to documentation
- **🔄 RPG Conversion**: Convert traditional RPG to free-form format
- **📊 Code Analysis**: Analyze RPG code structure and complexity
- **✅ Conversion Validation**: Validate conversions against standards
- **💡 Modernization**: Suggest improvements for legacy RPG code
- **Image Processing**: Extract and analyze images from PDF documents using PyMuPDF
- **Artifact Creation**: Generate large code artifacts with proper structure
- **Context Management**: Stay within 128K token limits with intelligent truncation
- **Azure OpenAI Integration**: Full integration with GPT-4o for code assistance

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Application                       │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ Azure OpenAI    │    │ Enhanced Python │                │
│  │ GPT-4o         │◄──►│ RPG Client      │                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────────────────┬───────────────────────────┘
                                  │ HTTP/MCP Protocol
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│              Enhanced MCP Server (FastAPI)                 │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ RPG Conversion  │    │ Document        │                │
│  │ Engine          │    │ Processing      │                │
│  │ • Analyze RPG   │    │ • PDF extraction│                │
│  │ • Convert Code  │    │ • Section extract│               │
│  │ • Validate      │    │ • Pattern recog │                │
│  │ • Modernize     │    │ • Standards     │                │
│  └─────────────────┘    └─────────────────┘                │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ Code Generation │    │ Enhanced        │                │
│  │ Tools           │    │ Analysis        │                │
│  │ • generate_code │    │ • Style compare │                │
│  │ • review_code   │    │ • Pattern extract│               │
│  │ • explain_code  │    │ • Code quality  │                │
│  │ • create_artifact│   │ • Standards ref │                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────────────────┬───────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│                 Enhanced Storage                            │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ Documents       │    │ Conversion      │                │
│  │ • Standards     │    │ Artifacts       │                │
│  │ • Conversion    │    │ • Original RPG  │                │
│  │   Guides        │    │ • Free-form     │                │
│  │ • Best Practices│    │ • Validation    │                │
│  │ • References    │    │ • Reports       │                │
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

### 2. Start the Enhanced MCP Server

```bash
# Run locally
python mcp-server.py

# Or using Docker
docker-compose up -d
```

### 3. Upload Reference Documents

```bash
# Upload coding standards and conversion guides
curl -X POST -F "file=@rpg_coding_standards.pdf" http://localhost:8000/upload
curl -X POST -F "file=@rpg_conversion_guide.md" http://localhost:8000/upload
curl -X POST -F "file=@freeform_best_practices.pdf" http://localhost:8000/upload
```

### 4. Run the Enhanced Client

```bash
# Interactive RPG conversion mode
python client.py interactive

# Example mode
python client.py
```

## Available Tools

### 🆕 Enhanced RPG Conversion Tools

#### 1. `analyze_rpg_syntax`
Analyze traditional RPG code structure and identify conversion requirements.

**Parameters:**
- `code`: Traditional RPG code to analyze
- `include_conversion_plan`: Include conversion strategy (default: true)

**Example:**
```python
await mcp_client.call_tool("analyze_rpg_syntax", {
    "code": traditional_rpg_code,
    "include_conversion_plan": True
})
```

#### 2. `convert_rpg_to_freeform`
Convert traditional RPG code to free-form format using uploaded coding standards.

**Parameters:**
- `code`: Traditional RPG code to convert
- `apply_standards`: Apply uploaded coding standards (default: true)
- `include_comments`: Include conversion comments (default: true)
- `validation_level`: Level of validation (basic/detailed/comprehensive)

#### 3. `validate_conversion`
Validate converted RPG code against uploaded standards and best practices.

**Parameters:**
- `original_code`: Original traditional RPG code
- `converted_code`: Converted free-form RPG code
- `standards_reference`: Specific standards document to reference

#### 4. `suggest_modernization`
Suggest modernization techniques for RPG code based on current best practices.

**Parameters:**
- `code`: RPG code to analyze for modernization
- `focus_areas`: Specific areas to focus on (error_handling, data_structures, procedures, sql_integration, performance, maintainability)

#### 5. `compare_code_styles`
Compare traditional and free-form RPG coding styles with examples from standards.

**Parameters:**
- `operation_type`: Type of operation to compare (file_operations, calculations, conditions, loops, procedures, error_handling)
- `show_examples`: Include code examples (default: true)

#### 6. `extract_rpg_patterns`
Extract specific RPG coding patterns and standards from reference documents.

**Parameters:**
- `pattern_type`: Type of RPG pattern to extract (naming_conventions, error_handling, file_operations, data_structures, procedures, conversion_rules)
- `format`: RPG format to focus on (traditional/freeform/both)

#### 7. `get_document_sections`
Retrieve specific sections from uploaded documents by title or content type.

**Parameters:**
- `section_title`: Title or header of the section to retrieve
- `document_name`: Specific document name (optional)
- `content_type`: Type of content to look for (coding_standards, conversion_rules, examples, best_practices, procedures)

### Enhanced Existing Tools

#### 8. `upload_document` (Enhanced)
Process uploaded PDF or Markdown documents with improved RPG detection.

**New document types:**
- `conversion_guide`: RPG conversion guides and migration documents
- Enhanced section extraction for coding standards
- Improved RPG code pattern recognition

#### 9. `extract_code_examples` (Enhanced)
Extract code examples with enhanced RPG format detection.

**New code types:**
- `rpg_traditional`: Traditional fixed-format RPG
- `rpg_freeform`: Modern free-form RPG

#### 10. `generate_code` (Enhanced)
Generate new code with improved RPG free-form generation.

**Enhanced code types:**
- `rpg_freeform`: Generate modern free-form RPG code

### Standard Tools (Unchanged)

11. `search_references` - Search through uploaded documents
12. `review_code` - Review code against standards  
13. `explain_code` - Explain code functionality
14. `create_artifact` - Create large code artifacts
15. `list_documents` - List uploaded documents

## Enhanced Usage Examples

### RPG Conversion Workflow

```python
# 1. Upload conversion standards
await mcp_client.upload_document("rpg_conversion_standards.pdf")
await mcp_client.call_tool("upload_document", {
    "filename": "rpg_conversion_standards.pdf",
    "document_type": "conversion_guide",
    "description": "Official RPG conversion standards"
})

# 2. Analyze traditional RPG code
traditional_code = """
H DFTACTGRP(*NO) ACTGRP(*CALLER)
F CUSTFILE  IF   E           K DISK
D customerID      S              7P 0
C                   CHAIN     12345         CUSTFILE
"""

analysis = await mcp_client.call_tool("analyze_rpg_syntax", {
    "code": traditional_code,
    "include_conversion_plan": True
})

# 3. Convert to free-form
conversion = await mcp_client.call_tool("convert_rpg_to_freeform", {
    "code": traditional_code,
    "apply_standards": True,
    "validation_level": "detailed"
})

# 4. Validate conversion
validation = await mcp_client.call_tool("validate_conversion", {
    "original_code": traditional_code,
    "converted_code": converted_code
})

# 5. Get modernization suggestions
suggestions = await mcp_client.call_tool("suggest_modernization", {
    "code": converted_code,
    "focus_areas": ["error_handling", "procedures", "sql_integration"]
})
```

### Document Analysis

```python
# Extract conversion patterns from standards
patterns = await mcp_client.call_tool("extract_rpg_patterns", {
    "pattern_type": "conversion_rules",
    "format": "both"
})

# Get specific document sections
standards = await mcp_client.call_tool("get_document_sections", {
    "section_title": "Free-form Conversion Rules",
    "content_type": "conversion_rules"
})

# Compare coding styles
comparison = await mcp_client.call_tool("compare_code_styles", {
    "operation_type": "file_operations",
    "show_examples": True
})
```

## Enhanced Interactive Commands

When running `python client.py interactive`:

### New RPG Conversion Commands
- `analyze <code>` - Analyze traditional RPG code structure
- `convert <code>` - Convert traditional RPG to free-form
- `validate` - Validate a conversion (prompts for both codes)
- `modernize <code>` - Get modernization suggestions
- `compare <operation>` - Compare traditional vs free-form styles
- `patterns <type>` - Extract RPG patterns from documents
- `sections <title>` - Get specific document sections
- `standards` - View conversion standards from documents

### Enhanced Existing Commands
- `upload <file_path>` - Upload with conversion guide support
- `generate <type> <requirements>` - Enhanced RPG generation
- `review <type> <code>` - Enhanced RPG code review
- `explain <code>` - Enhanced RPG code explanation
- `docs` - List documents with processing status
- `artifacts` - List artifacts including conversions

## Document Types

### Supported Formats
- **PDF**: Enhanced extraction with section recognition
- **Markdown**: Improved header and section processing

### Enhanced Document Categories
- **standards**: Coding standards and conventions
- **procedures**: Development procedures and workflows
- **best_practices**: Best practice guidelines
- **reference**: Technical reference materials
- **examples**: Code examples and templates
- **🆕 conversion_guide**: RPG conversion guides and migration documentation

## RPG Conversion Features

### Automatic Analysis
- **Format Detection**: Identifies traditional vs free-form RPG
- **Complexity Assessment**: Evaluates conversion difficulty
- **Component Inventory**: Catalogs H-specs, F-specs, D-specs, etc.
- **Dependency Analysis**: Identifies files, subroutines, and indicators

### Intelligent Conversion
- **Standards Application**: Uses uploaded coding standards
- **Structure Modernization**: Converts subroutines to procedures
- **Syntax Translation**: Fixed-format to free-form conversion
- **Error Handling Enhancement**: Adds modern error handling patterns

### Validation & Quality
- **Functional Validation**: Ensures converted code maintains functionality
- **Standards Compliance**: Validates against uploaded coding standards
- **Best Practice Checks**: Applies modern RPG best practices
- **Quality Assessment**: Provides code quality metrics

### Modernization Suggestions
- **Error Handling**: MONITOR/ON-ERROR patterns
- **Data Structures**: Qualified data structures
- **Procedures**: Modern procedure implementations
- **SQL Integration**: Embedded SQL recommendations
- **Performance**: Optimization suggestions

## Context Window Management

Enhanced system automatically manages the 128K token context window:

1. **Smart Content Truncation**: Intelligently truncates long documents while preserving key sections
2. **Conversion History**: Maintains conversion context for validation
3. **Standards Prioritization**: Keeps coding standards in context during conversions
4. **Artifact Generation**: Large conversions are automatically saved as artifacts

## Environment Variables

### Server Variables (Enhanced)
```bash
export MCP_SERVER_HOST="0.0.0.0"
export MCP_SERVER_PORT="8000"
export STORAGE_PATH="./storage"
export RPG_CONVERSION_ENABLED="true"  # New
export ENHANCED_ANALYSIS="true"       # New
```

### Client Variables (Enhanced)
```bash
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o"
export AZURE_OPENAI_API_VERSION="2024-02-01"
export MCP_SERVER_URL="http://localhost:8000"
export RPG_CONVERSION_MODE="enhanced"  # New
```

## API Endpoints

### Enhanced MCP Protocol
- `POST /mcp` - Main MCP protocol endpoint with RPG tools

### File Management (Enhanced)
- `POST /upload` - Upload documents including conversion guides
- `GET /documents` - List documents with processing status
- `GET /artifacts` - List artifacts including conversion results

### Health Check (Enhanced)
- `GET /health` - Server health with RPG conversion status
- `GET /` - Server information with new features

## Docker Deployment

```bash
# Build and run enhanced server
docker-compose up -d

# View logs
docker-compose logs -f mcp-server

# Stop
docker-compose down
```

## Development

### Adding New RPG Tools

1. Add tool definition in `list_tools()` function
2. Add implementation in `call_tool()` function
3. Update RPGConverter class for new conversion logic
4. Test with various RPG code samples

### Extending Conversion Engine

1. Enhance pattern recognition in `CodeAnalyzer`
2. Add new conversion rules in `RPGConverter`
3. Update validation logic
4. Add new modernization patterns

## RPG Conversion Examples

### Traditional RPG Input
```rpg
H DFTACTGRP(*NO) ACTGRP(*CALLER)
F CUSTFILE  IF   E           K DISK
F ORDERFILE UF   E           K DISK
D customerID      S              7P 0
D customerName    S             50A
D orderTotal      S             15P 2
C                   CHAIN     12345         CUSTFILE
C                   IF        %FOUND(CUSTFILE)
C                   EVAL      customerName = CFNAME
C     calcTotal    BEGSR
C                   EVAL      orderTotal = OAMT1 + OAMT2
C                   ENDSR
```

### Free-form Output
```rpg
**CTL-OPT DFTACTGRP(*NO) ACTGRP(*CALLER);

DCL-F CUSTFILE DISK(*EXT) USAGE(*INPUT) KEYED;
DCL-F ORDERFILE DISK(*EXT) USAGE(*UPDATE) KEYED;

DCL-S customerID PACKED(7:0);
DCL-S customerName CHAR(50);
DCL-S orderTotal PACKED(15:2);

// Main processing logic
CHAIN 12345 CUSTFILE;
IF %FOUND(CUSTFILE);
    customerName = CFNAME;
    calcTotal();
ENDIF;

DCL-PROC calcTotal;
    orderTotal = OAMT1 + OAMT2;
END-PROC;
```

## Troubleshooting

### Enhanced Issues

1. **RPG Conversion failures**: Check uploaded conversion standards
2. **Pattern recognition errors**: Verify document format and content
3. **Validation failures**: Ensure original and converted code are provided
4. **Standards not applied**: Verify document type is set correctly

### Performance Optimization

- Conversion results are cached for repeat operations
- Large conversions are automatically saved as artifacts
- Pattern extraction is optimized for speed
- Document sections are indexed for quick retrieval

## Security Considerations

- Uploaded RPG code is processed securely
- Conversion artifacts are properly isolated
- Standards documents are validated before processing
- Access controls for sensitive conversion guides

## Contributing

1. Fork the repository
2. Create feature branch for RPG enhancements
3. Add comprehensive tests for conversion logic
4. Update documentation for new tools
5. Submit pull request

## License

This enhanced project is provided as-is for educational and development purposes, with special focus on RPG modernization initiatives.

## Changelog

### v1.1.0 - Enhanced RPG Conversion
- ✨ Added traditional-to-freeform RPG conversion
- 🔍 Enhanced code analysis and pattern recognition  
- 📊 Added conversion validation tools
- 💡 Implemented modernization suggestions
- 📚 Enhanced document processing with section extraction
- 🎯 Added specialized RPG pattern extraction
- ⚡ Improved performance for large code conversions
- 🛠️ Enhanced interactive client for RPG workflows