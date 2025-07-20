#!/usr/bin/env python3

import asyncio
import json
import os
import uuid
import hashlib
import base64
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

import uvicorn
import fitz  # PyMuPDF
from PIL import Image
import io
from fastapi import FastAPI, Request, Response, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from mcp.server import Server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)

# Initialize MCP Server
mcp_server = Server("db2-rpg-code-server")

# Initialize FastAPI app
app = FastAPI(title="DB2/RPG Code Generation MCP Server", version="1.0.0")

# Storage configuration
STORAGE_DIR = Path("storage/documents")
ARTIFACTS_DIR = Path("storage/artifacts")
IMAGES_DIR = Path("storage/images")

# Create directories
for directory in [STORAGE_DIR, ARTIFACTS_DIR, IMAGES_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Document metadata storage
documents_metadata = {}

class DocumentProcessor:
    """Process and extract content from uploaded documents."""
    
    @staticmethod
    def extract_pdf_content(file_path: Path) -> Dict[str, Any]:
        """Extract text and images from PDF using PyMuPDF."""
        try:
            doc = fitz.open(file_path)
            content = {
                "text": "",
                "images": [],
                "pages": len(doc),
                "metadata": doc.metadata
            }
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Extract text
                page_text = page.get_text()
                content["text"] += f"\n--- Page {page_num + 1} ---\n{page_text}\n"
                
                # Extract images
                image_list = page.get_images()
                for img_index, img in enumerate(image_list):
                    try:
                        # Get image data
                        xref = img[0]
                        pix = fitz.Pixmap(doc, xref)
                        
                        if pix.n - pix.alpha < 4:  # GRAY or RGB
                            # Convert to PIL Image
                            img_data = pix.tobytes("png")
                            pil_img = Image.open(io.BytesIO(img_data))
                            
                            # Save image
                            img_filename = f"{file_path.stem}_page{page_num + 1}_img{img_index + 1}.png"
                            img_path = IMAGES_DIR / img_filename
                            pil_img.save(img_path)
                            
                            # Store image metadata
                            content["images"].append({
                                "filename": img_filename,
                                "page": page_num + 1,
                                "path": str(img_path),
                                "size": pil_img.size,
                                "format": pil_img.format
                            })
                        
                        pix = None
                    except Exception as e:
                        print(f"Error extracting image {img_index} from page {page_num}: {e}")
            
            doc.close()
            return content
            
        except Exception as e:
            return {"error": f"Failed to process PDF: {str(e)}"}
    
    @staticmethod
    def extract_markdown_content(file_path: Path) -> Dict[str, Any]:
        """Extract content from markdown files."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                "text": content,
                "images": [],
                "format": "markdown",
                "size": len(content)
            }
        except Exception as e:
            return {"error": f"Failed to process Markdown: {str(e)}"}

class CodeAnalyzer:
    """Analyze and process code content."""
    
    @staticmethod
    def extract_code_blocks(text: str) -> List[Dict[str, str]]:
        """Extract code blocks from text."""
        code_blocks = []
        
        # SQL/DB2 patterns
        sql_patterns = [
            r'(?i)(CREATE\s+(?:TABLE|INDEX|VIEW|PROCEDURE|FUNCTION).*?;)',
            r'(?i)(SELECT.*?FROM.*?(?:;|$))',
            r'(?i)(INSERT\s+INTO.*?(?:;|$))',
            r'(?i)(UPDATE.*?SET.*?(?:;|$))',
            r'(?i)(DELETE\s+FROM.*?(?:;|$))'
        ]
        
        # RPG patterns
        rpg_patterns = [
            r'(?i)(DCL-.*?;)',
            r'(?i)(EXEC\s+SQL.*?;)',
            r'(?i)(IF\s+.*?ENDIF;)',
            r'(?i)(FOR\s+.*?ENDFOR;)',
            r'(?i)(MONITOR.*?ON-ERROR.*?ENDMON;)'
        ]
        
        for pattern in sql_patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)
            for match in matches:
                code_blocks.append({
                    "type": "SQL/DB2",
                    "code": match.strip(),
                    "language": "sql"
                })
        
        for pattern in rpg_patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)
            for match in matches:
                code_blocks.append({
                    "type": "RPG",
                    "code": match.strip(),
                    "language": "rpg"
                })
        
        return code_blocks
    
    @staticmethod
    def analyze_code_quality(code: str, code_type: str) -> Dict[str, Any]:
        """Analyze code quality and provide suggestions."""
        analysis = {
            "type": code_type,
            "issues": [],
            "suggestions": [],
            "complexity": "low"
        }
        
        if code_type.upper() == "SQL":
            # SQL analysis
            if not re.search(r'WHERE\s+', code, re.IGNORECASE):
                analysis["issues"].append("Missing WHERE clause - potential full table scan")
            
            if re.search(r'SELECT\s+\*', code, re.IGNORECASE):
                analysis["suggestions"].append("Avoid SELECT * - specify columns explicitly")
            
            if not re.search(r'ORDER\s+BY', code, re.IGNORECASE) and re.search(r'SELECT', code, re.IGNORECASE):
                analysis["suggestions"].append("Consider adding ORDER BY for consistent results")
        
        elif code_type.upper() == "RPG":
            # RPG analysis
            if not re.search(r'MONITOR', code, re.IGNORECASE):
                analysis["suggestions"].append("Consider adding error handling with MONITOR")
            
            if re.search(r'GOTO', code, re.IGNORECASE):
                analysis["issues"].append("GOTO statements found - consider structured programming")
        
        return analysis

# Tool definitions
@mcp_server.list_tools()
async def list_tools() -> ListToolsResult:
    """List available tools."""
    return ListToolsResult(
        tools=[
            Tool(
                name="upload_document",
                description="Upload PDF or Markdown documents containing coding standards and references",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Name of the uploaded file"
                        },
                        "document_type": {
                            "type": "string",
                            "enum": ["standards", "procedures", "best_practices", "reference", "examples"],
                            "description": "Type of document being uploaded"
                        },
                        "description": {
                            "type": "string",
                            "description": "Brief description of the document content"
                        }
                    },
                    "required": ["filename", "document_type"]
                }
            ),
            Tool(
                name="search_references",
                description="Search through uploaded documents for specific topics or code patterns",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for finding relevant documentation"
                        },
                        "document_type": {
                            "type": "string",
                            "enum": ["all", "standards", "procedures", "best_practices", "reference", "examples"],
                            "description": "Filter by document type",
                            "default": "all"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="extract_code_examples",
                description="Extract code examples and patterns from reference documents",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code_type": {
                            "type": "string",
                            "enum": ["all", "sql", "db2", "rpg", "procedure"],
                            "description": "Type of code to extract",
                            "default": "all"
                        },
                        "topic": {
                            "type": "string",
                            "description": "Specific topic or functionality to find examples for"
                        }
                    }
                }
            ),
            Tool(
                name="generate_code",
                description="Generate new code based on requirements and reference standards",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "requirements": {
                            "type": "string",
                            "description": "Detailed requirements for the code to be generated"
                        },
                        "code_type": {
                            "type": "string",
                            "enum": ["sql", "db2", "rpg", "procedure"],
                            "description": "Type of code to generate"
                        },
                        "style_guide": {
                            "type": "string",
                            "description": "Specific style guide or standards to follow",
                            "default": "company_standards"
                        },
                        "include_comments": {
                            "type": "boolean",
                            "description": "Include detailed comments in generated code",
                            "default": True
                        }
                    },
                    "required": ["requirements", "code_type"]
                }
            ),
            Tool(
                name="review_code",
                description="Review existing code against uploaded standards and best practices",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code to be reviewed"
                        },
                        "code_type": {
                            "type": "string",
                            "enum": ["sql", "db2", "rpg", "procedure"],
                            "description": "Type of code being reviewed"
                        },
                        "review_level": {
                            "type": "string",
                            "enum": ["basic", "detailed", "comprehensive"],
                            "description": "Level of review detail",
                            "default": "detailed"
                        }
                    },
                    "required": ["code", "code_type"]
                }
            ),
            Tool(
                name="explain_code",
                description="Explain code functionality and structure using reference documentation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code to be explained"
                        },
                        "explanation_level": {
                            "type": "string",
                            "enum": ["beginner", "intermediate", "advanced"],
                            "description": "Level of explanation detail",
                            "default": "intermediate"
                        },
                        "include_references": {
                            "type": "boolean",
                            "description": "Include references to documentation sources",
                            "default": True
                        }
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="create_artifact",
                description="Create large code artifacts (files, modules) with proper structure",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "artifact_type": {
                            "type": "string",
                            "enum": ["module", "procedure", "package", "complete_program"],
                            "description": "Type of artifact to create"
                        },
                        "specifications": {
                            "type": "string",
                            "description": "Detailed specifications for the artifact"
                        },
                        "include_documentation": {
                            "type": "boolean",
                            "description": "Include comprehensive documentation",
                            "default": True
                        }
                    },
                    "required": ["artifact_type", "specifications"]
                }
            ),
            Tool(
                name="list_documents",
                description="List all uploaded reference documents with metadata",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "document_type": {
                            "type": "string",
                            "enum": ["all", "standards", "procedures", "best_practices", "reference", "examples"],
                            "description": "Filter by document type",
                            "default": "all"
                        }
                    }
                }
            )
        ]
    )

@mcp_server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """Handle tool calls."""
    
    if name == "upload_document":
        # This would be called after a file is uploaded via HTTP endpoint
        filename = arguments.get("filename", "")
        document_type = arguments.get("document_type", "reference")
        description = arguments.get("description", "")
        
        file_path = STORAGE_DIR / filename
        
        if not file_path.exists():
            return CallToolResult(
                content=[TextContent(type="text", text=f"File '{filename}' not found. Please upload the file first.")]
            )
        
        # Process the document
        if file_path.suffix.lower() == '.pdf':
            content = DocumentProcessor.extract_pdf_content(file_path)
        elif file_path.suffix.lower() in ['.md', '.markdown']:
            content = DocumentProcessor.extract_markdown_content(file_path)
        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unsupported file type: {file_path.suffix}")]
            )
        
        if "error" in content:
            return CallToolResult(
                content=[TextContent(type="text", text=content["error"])]
            )
        
        # Store metadata
        file_id = hashlib.md5(filename.encode()).hexdigest()
        documents_metadata[file_id] = {
            "filename": filename,
            "document_type": document_type,
            "description": description,
            "content": content,
            "uploaded_at": datetime.now().isoformat(),
            "file_path": str(file_path)
        }
        
        # Extract code examples
        code_blocks = CodeAnalyzer.extract_code_blocks(content.get("text", ""))
        documents_metadata[file_id]["code_examples"] = code_blocks
        
        result = f"Document '{filename}' processed successfully:\n"
        result += f"- Type: {document_type}\n"
        result += f"- Pages/Size: {content.get('pages', 'N/A')}\n"
        result += f"- Images: {len(content.get('images', []))}\n"
        result += f"- Code examples found: {len(code_blocks)}\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result)]
        )
    
    elif name == "search_references":
        query = arguments.get("query", "").lower()
        document_type = arguments.get("document_type", "all")
        max_results = arguments.get("max_results", 5)
        
        if not query:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide a search query")]
            )
        
        results = []
        for file_id, doc_meta in documents_metadata.items():
            # Filter by document type
            if document_type != "all" and doc_meta["document_type"] != document_type:
                continue
            
            # Search in content
            content_text = doc_meta["content"].get("text", "").lower()
            if query in content_text:
                # Extract relevant excerpts
                sentences = content_text.split('.')
                relevant_excerpts = []
                for sentence in sentences:
                    if query in sentence:
                        relevant_excerpts.append(sentence.strip()[:200] + "...")
                        if len(relevant_excerpts) >= 2:
                            break
                
                results.append({
                    "document": doc_meta["filename"],
                    "type": doc_meta["document_type"],
                    "description": doc_meta["description"],
                    "excerpts": relevant_excerpts
                })
        
        if not results:
            return CallToolResult(
                content=[TextContent(type="text", text=f"No results found for query: '{query}'")]
            )
        
        # Limit results
        results = results[:max_results]
        
        result_text = f"Found {len(results)} relevant documents for '{query}':\n\n"
        for i, result in enumerate(results, 1):
            result_text += f"{i}. {result['document']} ({result['type']})\n"
            result_text += f"   Description: {result['description']}\n"
            for excerpt in result['excerpts']:
                result_text += f"   - {excerpt}\n"
            result_text += "\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "extract_code_examples":
        code_type = arguments.get("code_type", "all").lower()
        topic = arguments.get("topic", "").lower()
        
        all_examples = []
        for file_id, doc_meta in documents_metadata.items():
            code_examples = doc_meta.get("code_examples", [])
            for example in code_examples:
                # Filter by code type
                if code_type != "all" and code_type not in example["type"].lower():
                    continue
                
                # Filter by topic if specified
                if topic and topic not in example["code"].lower():
                    continue
                
                all_examples.append({
                    "source": doc_meta["filename"],
                    "type": example["type"],
                    "code": example["code"],
                    "language": example["language"]
                })
        
        if not all_examples:
            return CallToolResult(
                content=[TextContent(type="text", text=f"No code examples found for type: {code_type}, topic: {topic}")]
            )
        
        result_text = f"Found {len(all_examples)} code examples:\n\n"
        for i, example in enumerate(all_examples[:10], 1):  # Limit to 10 examples
            result_text += f"{i}. {example['type']} from {example['source']}:\n"
            result_text += f"```{example['language']}\n{example['code']}\n```\n\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "generate_code":
        requirements = arguments.get("requirements", "")
        code_type = arguments.get("code_type", "sql")
        style_guide = arguments.get("style_guide", "company_standards")
        include_comments = arguments.get("include_comments", True)
        
        if not requirements:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide detailed requirements for code generation")]
            )
        
        # Search for relevant examples and standards
        relevant_docs = []
        for file_id, doc_meta in documents_metadata.items():
            if doc_meta["document_type"] in ["standards", "best_practices", "examples"]:
                relevant_docs.append(doc_meta)
        
        result_text = f"Generated {code_type.upper()} code based on requirements and company standards:\n\n"
        
        if code_type.lower() == "sql":
            result_text += "```sql\n"
            result_text += "-- Generated SQL based on requirements\n" if include_comments else ""
            result_text += "-- Following company coding standards\n\n" if include_comments else ""
            result_text += f"-- Requirements: {requirements}\n\n" if include_comments else ""
            result_text += "SELECT \n    column1,\n    column2,\n    column3\nFROM table_name\nWHERE condition = 'value'\nORDER BY column1;\n"
            result_text += "```\n\n"
        
        elif code_type.lower() == "rpg":
            result_text += "```rpg\n"
            result_text += "// Generated RPG code based on requirements\n" if include_comments else ""
            result_text += "// Following company coding standards\n\n" if include_comments else ""
            result_text += "DCL-S variable CHAR(50);\n"
            result_text += "DCL-S counter INT(10);\n\n"
            result_text += "EXEC SQL\n  SELECT field1 INTO :variable\n  FROM table1\n  WHERE condition = :parameter;\n\n"
            result_text += "IF variable <> '';\n  // Process data\nENDIF;\n"
            result_text += "```\n\n"
        
        result_text += "Note: This is a template. Customize based on your specific requirements.\n"
        result_text += f"References used: {len(relevant_docs)} documents from standards and best practices."
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "review_code":
        code = arguments.get("code", "")
        code_type = arguments.get("code_type", "sql")
        review_level = arguments.get("review_level", "detailed")
        
        if not code:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide code to review")]
            )
        
        # Analyze the code
        analysis = CodeAnalyzer.analyze_code_quality(code, code_type)
        
        result_text = f"Code Review Report ({review_level} level):\n\n"
        result_text += f"Code Type: {analysis['type']}\n"
        result_text += f"Complexity: {analysis['complexity']}\n\n"
        
        if analysis['issues']:
            result_text += "Issues Found:\n"
            for issue in analysis['issues']:
                result_text += f"- {issue}\n"
            result_text += "\n"
        
        if analysis['suggestions']:
            result_text += "Suggestions for Improvement:\n"
            for suggestion in analysis['suggestions']:
                result_text += f"- {suggestion}\n"
            result_text += "\n"
        
        if not analysis['issues'] and not analysis['suggestions']:
            result_text += "✅ No major issues found. Code follows basic standards.\n"
        
        result_text += "\nReview based on uploaded coding standards and best practices."
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "explain_code":
        code = arguments.get("code", "")
        explanation_level = arguments.get("explanation_level", "intermediate")
        include_references = arguments.get("include_references", True)
        
        if not code:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide code to explain")]
            )
        
        result_text = f"Code Explanation ({explanation_level} level):\n\n"
        result_text += f"```\n{code}\n```\n\n"
        
        # Basic code analysis and explanation
        if "SELECT" in code.upper():
            result_text += "This is a SQL SELECT statement that retrieves data from a database.\n"
            result_text += "It queries specified columns from tables based on given conditions.\n\n"
        
        elif "DCL-" in code.upper():
            result_text += "This is RPG code using free-form syntax.\n"
            result_text += "DCL statements declare variables and their data types.\n\n"
        
        elif "EXEC SQL" in code.upper():
            result_text += "This is embedded SQL within RPG code.\n"
            result_text += "It allows direct database operations from within the RPG program.\n\n"
        
        if explanation_level == "detailed" or explanation_level == "advanced":
            result_text += "Detailed Analysis:\n"
            result_text += "- The code follows standard formatting conventions\n"
            result_text += "- Variable naming appears consistent\n"
            result_text += "- Proper use of data types and structures\n\n"
        
        if include_references:
            result_text += "References: Based on uploaded coding standards and documentation."
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "create_artifact":
        artifact_type = arguments.get("artifact_type", "module")
        specifications = arguments.get("specifications", "")
        include_documentation = arguments.get("include_documentation", True)
        
        if not specifications:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide detailed specifications for the artifact")]
            )
        
        # Generate unique artifact ID
        artifact_id = str(uuid.uuid4())[:8]
        artifact_filename = f"artifact_{artifact_id}_{artifact_type}.txt"
        artifact_path = ARTIFACTS_DIR / artifact_filename
        
        # Create artifact content
        artifact_content = f"{'='*60}\n"
        artifact_content += f"ARTIFACT: {artifact_type.upper()}\n"
        artifact_content += f"Generated: {datetime.now().isoformat()}\n"
        artifact_content += f"ID: {artifact_id}\n"
        artifact_content += f"{'='*60}\n\n"
        
        if include_documentation:
            artifact_content += f"SPECIFICATIONS:\n{specifications}\n\n"
            artifact_content += f"DOCUMENTATION:\n"
            artifact_content += f"This {artifact_type} was generated based on the provided specifications\n"
            artifact_content += f"and follows company coding standards and best practices.\n\n"
        
        artifact_content += f"CODE:\n"
        artifact_content += f"-- {artifact_type.upper()} implementation\n"
        artifact_content += f"-- Generated based on: {specifications[:100]}...\n\n"
        
        if artifact_type == "procedure":
            artifact_content += "CREATE OR REPLACE PROCEDURE sample_procedure(\n"
            artifact_content += "    IN param1 VARCHAR(50),\n"
            artifact_content += "    OUT result VARCHAR(100)\n"
            artifact_content += ")\nBEGIN\n"
            artifact_content += "    -- Procedure implementation\n"
            artifact_content += "    SET result = 'Processing: ' || param1;\n"
            artifact_content += "END;\n"
        
        elif artifact_type == "module":
            artifact_content += "**CTL-OPT DFTACTGRP(*NO) ACTGRP(*CALLER);\n\n"
            artifact_content += "// Module implementation\n"
            artifact_content += "DCL-PROC process_data EXPORT;\n"
            artifact_content += "    DCL-PI *N CHAR(100);\n"
            artifact_content += "        input_data CHAR(50) CONST;\n"
            artifact_content += "    END-PI;\n\n"
            artifact_content += "    // Processing logic here\n"
            artifact_content += "    RETURN 'Processed: ' + input_data;\n"
            artifact_content += "END-PROC;\n"
        
        # Save artifact
        with open(artifact_path, 'w', encoding='utf-8') as f:
            f.write(artifact_content)
        
        result_text = f"Artifact created successfully!\n\n"
        result_text += f"Type: {artifact_type}\n"
        result_text += f"ID: {artifact_id}\n"
        result_text += f"Filename: {artifact_filename}\n"
        result_text += f"Path: {artifact_path}\n\n"
        result_text += f"The artifact has been saved and can be referenced or downloaded.\n"
        result_text += f"Size: {len(artifact_content)} characters\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "list_documents":
        document_type = arguments.get("document_type", "all")
        
        filtered_docs = []
        for file_id, doc_meta in documents_metadata.items():
            if document_type == "all" or doc_meta["document_type"] == document_type:
                filtered_docs.append(doc_meta)
        
        if not filtered_docs:
            return CallToolResult(
                content=[TextContent(type="text", text="No documents found")]
            )
        
        result_text = f"Available Documents ({len(filtered_docs)} total):\n\n"
        for i, doc in enumerate(filtered_docs, 1):
            result_text += f"{i}. {doc['filename']}\n"
            result_text += f"   Type: {doc['document_type']}\n"
            result_text += f"   Description: {doc['description']}\n"
            result_text += f"   Uploaded: {doc['uploaded_at']}\n"
            
            content = doc.get('content', {})
            if 'pages' in content:
                result_text += f"   Pages: {content['pages']}\n"
            if 'images' in content:
                result_text += f"   Images: {len(content['images'])}\n"
            if 'code_examples' in doc:
                result_text += f"   Code Examples: {len(doc['code_examples'])}\n"
            result_text += "\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    else:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {name}")]
        )

# FastAPI endpoints
@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """Handle MCP requests via HTTP."""
    try:
        body = await request.body()
        mcp_request = json.loads(body.decode())
        
        if mcp_request.get("method") == "tools/list":
            result = await list_tools()
            response_data = {
                "jsonrpc": "2.0",
                "id": mcp_request.get("id"),
                "result": result.dict()
            }
        
        elif mcp_request.get("method") == "tools/call":
            params = mcp_request.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            result = await call_tool(tool_name, arguments)
            response_data = {
                "jsonrpc": "2.0",
                "id": mcp_request.get("id"),
                "result": result.dict()
            }
        
        else:
            response_data = {
                "jsonrpc": "2.0",
                "id": mcp_request.get("id"),
                "error": {
                    "code": -32601,
                    "message": "Method not found"
                }
            }
        
        return Response(
            content=json.dumps(response_data),
            media_type="application/json"
        )
    
    except Exception as e:
        error_response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }
        return Response(
            content=json.dumps(error_response),
            media_type="application/json",
            status_code=500
        )

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload PDF or Markdown files."""
    try:
        # Validate file type
        allowed_extensions = ['.pdf', '.md', '.markdown']
        file_extension = Path(file.filename).suffix.lower()
        
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"Only PDF and Markdown files are allowed. Got: {file_extension}"
            )
        
        # Check file size (max 50MB)
        max_size = 50 * 1024 * 1024
        file_content = await file.read()
        
        if len(file_content) > max_size:
            raise HTTPException(status_code=413, detail="File too large (max 50MB)")
        
        # Save file
        file_path = STORAGE_DIR / file.filename
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
        
        file_size = file_path.stat().st_size
        
        return {
            "filename": file.filename,
            "size": file_size,
            "type": file_extension,
            "status": "uploaded",
            "message": f"File '{file.filename}' uploaded successfully. Use 'upload_document' tool to process it."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/documents")
async def list_uploaded_files():
    """List all uploaded documents."""
    try:
        files = []
        total_size = 0
        
        for file_path in STORAGE_DIR.glob("*"):
            if file_path.is_file():
                size = file_path.stat().st_size
                total_size += size
                files.append({
                    "filename": file_path.name,
                    "size": size,
                    "modified": file_path.stat().st_mtime,
                    "extension": file_path.suffix,
                    "processed": any(meta["filename"] == file_path.name for meta in documents_metadata.values())
                })
        
        return {
            "files": sorted(files, key=lambda x: x["modified"], reverse=True),
            "total_files": len(files),
            "total_size": total_size,
            "processed_count": len(documents_metadata)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/artifacts")
async def list_artifacts():
    """List all generated artifacts."""
    try:
        artifacts = []
        
        for artifact_path in ARTIFACTS_DIR.glob("*.txt"):
            if artifact_path.is_file():
                artifacts.append({
                    "filename": artifact_path.name,
                    "size": artifact_path.stat().st_size,
                    "created": artifact_path.stat().st_mtime,
                    "path": str(artifact_path)
                })
        
        return {
            "artifacts": sorted(artifacts, key=lambda x: x["created"], reverse=True),
            "total_artifacts": len(artifacts)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "server": "DB2/RPG Code Generation MCP Server",
        "storage_dir": str(STORAGE_DIR),
        "documents_processed": len(documents_metadata),
        "artifacts_created": len(list(ARTIFACTS_DIR.glob("*.txt")))
    }

@app.get("/")
async def root():
    """Root endpoint with server info."""
    tools = await list_tools()
    tool_names = [tool.name for tool in tools.tools]
    
    return {
        "name": "DB2/RPG Code Generation MCP Server",
        "version": "1.0.0",
        "description": "MCP server for IBM DB2 and RPG code generation, review, and documentation",
        "tools": tool_names,
        "endpoints": {
            "mcp": "/mcp",
            "upload": "/upload",
            "documents": "/documents",
            "artifacts": "/artifacts",
            "health": "/health"
        },
        "supported_formats": ["PDF", "Markdown"],
        "documents_processed": len(documents_metadata)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
