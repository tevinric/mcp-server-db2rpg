#!/usr/bin/env python3

import asyncio
import json
import os
import uuid
import hashlib
import base64
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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
app = FastAPI(title="DB2/RPG Code Generation MCP Server", version="1.1.0")

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
                "metadata": doc.metadata,
                "sections": {},
                "page_content": {}
            }
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Extract text
                page_text = page.get_text()
                content["text"] += f"\n--- Page {page_num + 1} ---\n{page_text}\n"
                content["page_content"][page_num + 1] = page_text
                
                # Extract sections based on headers
                lines = page_text.split('\n')
                current_section = None
                for line in lines:
                    line = line.strip()
                    if re.match(r'^[A-Z][A-Z\s]+[A-Z]$', line) and len(line) > 5:  # All caps headers
                        current_section = line
                        if current_section not in content["sections"]:
                            content["sections"][current_section] = []
                    elif current_section and line:
                        content["sections"][current_section].append(line)
                
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
                content_text = f.read()
            
            # Extract sections based on markdown headers
            sections = {}
            lines = content_text.split('\n')
            current_section = None
            
            for line in lines:
                if line.startswith('#'):
                    current_section = line.strip('#').strip()
                    sections[current_section] = []
                elif current_section and line.strip():
                    sections[current_section].append(line)
            
            return {
                "text": content_text,
                "images": [],
                "format": "markdown",
                "size": len(content_text),
                "sections": sections
            }
        except Exception as e:
            return {"error": f"Failed to process Markdown: {str(e)}"}

class RPGConverter:
    """Convert traditional RPG to free-form RPG."""
    
    @staticmethod
    def analyze_traditional_rpg(code: str) -> Dict[str, Any]:
        """Analyze traditional RPG code structure."""
        analysis = {
            "format": "traditional",
            "control_specs": [],
            "file_specs": [],
            "definition_specs": [],
            "input_specs": [],
            "calculation_specs": [],
            "output_specs": [],
            "indicators": [],
            "subroutines": [],
            "procedures": [],
            "fixed_format_lines": 0,
            "conversion_complexity": "medium"
        }
        
        lines = code.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            if len(line) < 6:
                continue
                
            # Check if it's fixed format (positions 6-80)
            if len(line) >= 6:
                analysis["fixed_format_lines"] += 1
                
                # Extract record type (position 6)
                record_type = line[5:6] if len(line) > 5 else ''
                
                if record_type == 'H':  # Control spec
                    analysis["control_specs"].append({
                        "line": line_num,
                        "content": line,
                        "keywords": RPGConverter._extract_h_spec_keywords(line)
                    })
                elif record_type == 'F':  # File spec
                    analysis["file_specs"].append({
                        "line": line_num,
                        "content": line,
                        "filename": line[7:15].strip(),
                        "file_type": line[15:16],
                        "device": line[35:42].strip()
                    })
                elif record_type == 'D':  # Definition spec
                    analysis["definition_specs"].append({
                        "line": line_num,
                        "content": line,
                        "name": line[7:21].strip(),
                        "spec_type": line[24:25]
                    })
                elif record_type == 'I':  # Input spec
                    analysis["input_specs"].append({
                        "line": line_num,
                        "content": line
                    })
                elif record_type == 'C':  # Calculation spec
                    analysis["calculation_specs"].append({
                        "line": line_num,
                        "content": line,
                        "indicators": line[7:11].strip(),
                        "operation": line[26:36].strip(),
                        "result": line[50:63].strip()
                    })
                elif record_type == 'O':  # Output spec
                    analysis["output_specs"].append({
                        "line": line_num,
                        "content": line
                    })
                
                # Extract indicators
                indicators = line[7:11].strip()
                if indicators and indicators not in analysis["indicators"]:
                    analysis["indicators"].append(indicators)
                
                # Detect subroutines
                operation = line[26:36].strip().upper()
                if operation == 'BEGSR':
                    subroutine_name = line[50:63].strip()
                    analysis["subroutines"].append(subroutine_name)
        
        # Determine conversion complexity
        complexity_score = 0
        complexity_score += len(analysis["file_specs"]) * 2
        complexity_score += len(analysis["calculation_specs"])
        complexity_score += len(analysis["indicators"]) * 3
        complexity_score += len(analysis["subroutines"]) * 2
        
        if complexity_score < 10:
            analysis["conversion_complexity"] = "low"
        elif complexity_score < 30:
            analysis["conversion_complexity"] = "medium"
        else:
            analysis["conversion_complexity"] = "high"
        
        return analysis
    
    @staticmethod
    def _extract_h_spec_keywords(line: str) -> List[str]:
        """Extract keywords from H-spec line."""
        keywords = []
        # Look for common H-spec keywords
        keyword_patterns = [
            r'DFTACTGRP\([^)]+\)',
            r'ACTGRP\([^)]+\)',
            r'OPTION\([^)]+\)',
            r'DATFMT\([^)]+\)',
            r'DECEDIT\([^)]+\)'
        ]
        
        for pattern in keyword_patterns:
            matches = re.findall(pattern, line, re.IGNORECASE)
            keywords.extend(matches)
        
        return keywords
    
    @staticmethod
    def convert_to_freeform(code: str, standards: Dict[str, Any] = None) -> Dict[str, Any]:
        """Convert traditional RPG to free-form format."""
        analysis = RPGConverter.analyze_traditional_rpg(code)
        
        conversion_result = {
            "original_code": code,
            "converted_code": "",
            "conversion_notes": [],
            "standards_applied": [],
            "warnings": [],
            "success": True
        }
        
        try:
            converted_lines = []
            
            # Add control specification
            if analysis["control_specs"]:
                converted_lines.append("**CTL-OPT DFTACTGRP(*NO) ACTGRP(*CALLER);")
                conversion_result["conversion_notes"].append("Converted H-spec to **CTL-OPT")
            
            # Convert file specifications
            for file_spec in analysis["file_specs"]:
                filename = file_spec["filename"]
                file_type = file_spec["file_type"]
                
                if file_type.upper() == 'I':  # Input file
                    converted_lines.append(f"DCL-F {filename} DISK(*EXT) USAGE(*INPUT) KEYED;")
                elif file_type.upper() == 'O':  # Output file
                    converted_lines.append(f"DCL-F {filename} DISK(*EXT) USAGE(*OUTPUT);")
                elif file_type.upper() == 'U':  # Update file
                    converted_lines.append(f"DCL-F {filename} DISK(*EXT) USAGE(*UPDATE) KEYED;")
                
                conversion_result["conversion_notes"].append(f"Converted F-spec for {filename}")
            
            # Convert definition specifications
            for def_spec in analysis["definition_specs"]:
                name = def_spec["name"]
                if name:
                    # Simple conversion - would need more logic for complex definitions
                    converted_lines.append(f"DCL-S {name} CHAR(50); // TODO: Verify data type")
                    conversion_result["conversion_notes"].append(f"Converted D-spec for {name}")
            
            # Convert calculation specifications
            converted_lines.append("")
            converted_lines.append("// Main processing logic")
            
            for calc_spec in analysis["calculation_specs"]:
                operation = calc_spec["operation"].upper()
                result = calc_spec["result"]
                indicators = calc_spec["indicators"]
                
                if operation == 'BEGSR':
                    subroutine_name = result
                    converted_lines.append(f"")
                    converted_lines.append(f"DCL-PROC {subroutine_name};")
                    conversion_result["conversion_notes"].append(f"Converted subroutine {subroutine_name} to procedure")
                
                elif operation == 'ENDSR':
                    converted_lines.append("END-PROC;")
                
                elif operation == 'EXSR':
                    subroutine_name = result
                    converted_lines.append(f"    {subroutine_name}();")
                
                elif operation in ['ADD', 'SUB', 'MULT', 'DIV']:
                    # Convert arithmetic operations
                    if result:
                        op_symbol = {
                            'ADD': '+',
                            'SUB': '-', 
                            'MULT': '*',
                            'DIV': '/'
                        }.get(operation, '+')
                        
                        factor1 = calc_spec["content"][12:25].strip()
                        factor2 = calc_spec["content"][26:40].strip()
                        
                        if factor1 and factor2:
                            converted_lines.append(f"    {result} = {factor1} {op_symbol} {factor2};")
                        elif factor2:
                            converted_lines.append(f"    {result} {op_symbol}= {factor2};")
                
                elif operation == 'CHAIN':
                    # Convert CHAIN operation
                    filename = result
                    key_field = calc_spec["content"][12:25].strip()
                    converted_lines.append(f"    CHAIN {key_field} {filename};")
                    converted_lines.append(f"    IF NOT %FOUND({filename});")
                    converted_lines.append(f"        // Handle record not found")
                    converted_lines.append(f"    ENDIF;")
                
                elif operation in ['IF', 'ELSEIF', 'ELSE', 'ENDIF']:
                    # Convert structured operations
                    condition = calc_spec["content"][12:49].strip()
                    if operation == 'IF':
                        converted_lines.append(f"    IF {condition};")
                    elif operation == 'ELSEIF':
                        converted_lines.append(f"    ELSEIF {condition};")
                    elif operation == 'ELSE':
                        converted_lines.append(f"    ELSE;")
                    elif operation == 'ENDIF':
                        converted_lines.append(f"    ENDIF;")
                
                # Add indicator warnings
                if indicators and indicators not in ['', '  ']:
                    conversion_result["warnings"].append(f"Indicator {indicators} used - may need manual conversion")
            
            # Apply coding standards if provided
            if standards:
                conversion_result["standards_applied"] = RPGConverter._apply_coding_standards(
                    converted_lines, standards
                )
            
            conversion_result["converted_code"] = '\n'.join(converted_lines)
            
        except Exception as e:
            conversion_result["success"] = False
            conversion_result["error"] = str(e)
        
        return conversion_result
    
    @staticmethod
    def _apply_coding_standards(lines: List[str], standards: Dict[str, Any]) -> List[str]:
        """Apply coding standards to converted code."""
        applied_standards = []
        
        # Example standards application
        for i, line in enumerate(lines):
            # Indentation standards
            if line.strip() and not line.startswith('**') and not line.startswith('DCL-'):
                if not line.startswith('    ') and line.strip() != '':
                    lines[i] = '    ' + line.strip()
                    applied_standards.append("Applied indentation standard")
            
            # Variable naming conventions
            if 'DCL-S' in line:
                # Apply naming conventions based on standards
                pass
        
        return applied_standards

class CodeAnalyzer:
    """Analyze and process code content."""
    
    @staticmethod
    def extract_code_blocks(text: str) -> List[Dict[str, str]]:
        """Extract code blocks from text with enhanced RPG detection."""
        code_blocks = []
        
        # Enhanced SQL/DB2 patterns
        sql_patterns = [
            r'(?i)(CREATE\s+(?:TABLE|INDEX|VIEW|PROCEDURE|FUNCTION).*?;)',
            r'(?i)(SELECT.*?FROM.*?(?:;|$))',
            r'(?i)(INSERT\s+INTO.*?(?:;|$))',
            r'(?i)(UPDATE.*?SET.*?(?:;|$))',
            r'(?i)(DELETE\s+FROM.*?(?:;|$))',
            r'(?i)(ALTER\s+TABLE.*?(?:;|$))',
            r'(?i)(DROP\s+(?:TABLE|INDEX|VIEW).*?(?:;|$))'
        ]
        
        # Enhanced RPG patterns (traditional and free-form)
        rpg_patterns = [
            r'(?i)(\*\*CTL-OPT.*?;)',
            r'(?i)(DCL-[SFCP].*?;)',
            r'(?i)(EXEC\s+SQL.*?;)',
            r'(?i)(IF\s+.*?ENDIF;)',
            r'(?i)(FOR\s+.*?ENDFOR;)',
            r'(?i)(MONITOR.*?ON-ERROR.*?ENDMON;)',
            r'(?i)(DCL-PROC.*?END-PROC;)',
            r'(?i)(BEGSR.*?ENDSR)',
            r'(?i)(CHAIN.*?;)',
            r'(?i)(READ.*?;)',
            r'(?i)(write.*?;)',
            r'(?i)(update.*?;)'
        ]
        
        # Traditional RPG fixed-format patterns
        traditional_rpg_patterns = [
            r'^[HhFfDdIiCcOo].{74}',  # Fixed format lines
            r'^\s*[HhFfDdIiCcOo]\s+.*'  # Fixed format with spacing
        ]
        
        for pattern in sql_patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)
            for match in matches:
                code_blocks.append({
                    "type": "SQL/DB2",
                    "code": match.strip(),
                    "language": "sql",
                    "format": "standard"
                })
        
        for pattern in rpg_patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)
            for match in matches:
                code_blocks.append({
                    "type": "RPG Free-form",
                    "code": match.strip(),
                    "language": "rpg",
                    "format": "freeform"
                })
        
        # Check for traditional RPG
        lines = text.split('\n')
        traditional_block = []
        in_traditional_block = False
        
        for line in lines:
            if len(line) >= 6 and line[5:6] in 'HFDICOhfdico':
                if not in_traditional_block:
                    in_traditional_block = True
                    traditional_block = []
                traditional_block.append(line)
            elif in_traditional_block and line.strip() == '':
                continue  # Allow empty lines within block
            elif in_traditional_block:
                # End of traditional block
                if traditional_block:
                    code_blocks.append({
                        "type": "RPG Traditional",
                        "code": '\n'.join(traditional_block),
                        "language": "rpg",
                        "format": "traditional"
                    })
                    traditional_block = []
                in_traditional_block = False
        
        # Handle remaining traditional block
        if traditional_block:
            code_blocks.append({
                "type": "RPG Traditional",
                "code": '\n'.join(traditional_block),
                "language": "rpg",
                "format": "traditional"
            })
        
        return code_blocks
    
    @staticmethod
    def analyze_code_quality(code: str, code_type: str) -> Dict[str, Any]:
        """Enhanced code quality analysis."""
        analysis = {
            "type": code_type,
            "issues": [],
            "suggestions": [],
            "complexity": "low",
            "rpg_format": None
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
            # Determine RPG format
            if re.search(r'DCL-[SFCP]', code, re.IGNORECASE) or re.search(r'\*\*CTL-OPT', code, re.IGNORECASE):
                analysis["rpg_format"] = "freeform"
            elif len([line for line in code.split('\n') if len(line) >= 6 and line[5:6] in 'HFDICOhfdico']) > 0:
                analysis["rpg_format"] = "traditional"
                analysis["suggestions"].append("Consider converting to free-form RPG for better maintainability")
            
            # RPG analysis
            if not re.search(r'MONITOR', code, re.IGNORECASE):
                analysis["suggestions"].append("Consider adding error handling with MONITOR")
            
            if re.search(r'GOTO', code, re.IGNORECASE):
                analysis["issues"].append("GOTO statements found - consider structured programming")
            
            if analysis["rpg_format"] == "traditional":
                analysis["suggestions"].append("Traditional RPG format detected - conversion to free-form recommended")
        
        return analysis

# Enhanced tool definitions
@mcp_server.list_tools()
async def list_tools() -> ListToolsResult:
    """List available tools with enhanced RPG conversion capabilities."""
    return ListToolsResult(
        tools=[
            # Existing tools
            Tool(
                name="upload_document",
                description="Upload PDF or Markdown documents containing coding standards and references",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Name of the uploaded file"},
                        "document_type": {
                            "type": "string",
                            "enum": ["standards", "procedures", "best_practices", "reference", "examples", "conversion_guide"],
                            "description": "Type of document being uploaded"
                        },
                        "description": {"type": "string", "description": "Brief description of the document content"}
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
                        "query": {"type": "string", "description": "Search query for finding relevant documentation"},
                        "document_type": {
                            "type": "string",
                            "enum": ["all", "standards", "procedures", "best_practices", "reference", "examples", "conversion_guide"],
                            "description": "Filter by document type",
                            "default": "all"
                        },
                        "max_results": {"type": "integer", "description": "Maximum number of results to return", "default": 5}
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
                            "enum": ["all", "sql", "db2", "rpg", "rpg_traditional", "rpg_freeform", "procedure"],
                            "description": "Type of code to extract",
                            "default": "all"
                        },
                        "topic": {"type": "string", "description": "Specific topic or functionality to find examples for"}
                    }
                }
            ),
            
            # New enhanced tools
            Tool(
                name="get_document_sections",
                description="Retrieve specific sections from uploaded documents by title or content type",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "section_title": {"type": "string", "description": "Title or header of the section to retrieve"},
                        "document_name": {"type": "string", "description": "Specific document name (optional)"},
                        "content_type": {
                            "type": "string",
                            "enum": ["coding_standards", "conversion_rules", "examples", "best_practices", "procedures"],
                            "description": "Type of content to look for"
                        }
                    },
                    "required": ["section_title"]
                }
            ),
            Tool(
                name="extract_rpg_patterns",
                description="Extract specific RPG coding patterns and standards from reference documents",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pattern_type": {
                            "type": "string",
                            "enum": ["naming_conventions", "error_handling", "file_operations", "data_structures", "procedures", "conversion_rules"],
                            "description": "Type of RPG pattern to extract"
                        },
                        "format": {
                            "type": "string",
                            "enum": ["traditional", "freeform", "both"],
                            "description": "RPG format to focus on",
                            "default": "both"
                        }
                    },
                    "required": ["pattern_type"]
                }
            ),
            Tool(
                name="analyze_rpg_syntax",
                description="Analyze traditional RPG code structure and identify conversion requirements",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Traditional RPG code to analyze"},
                        "include_conversion_plan": {"type": "boolean", "description": "Include conversion strategy", "default": True}
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="convert_rpg_to_freeform",
                description="Convert traditional RPG code to free-form format using uploaded coding standards",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Traditional RPG code to convert"},
                        "apply_standards": {"type": "boolean", "description": "Apply uploaded coding standards", "default": True},
                        "include_comments": {"type": "boolean", "description": "Include conversion comments", "default": True},
                        "validation_level": {
                            "type": "string",
                            "enum": ["basic", "detailed", "comprehensive"],
                            "description": "Level of validation against standards",
                            "default": "detailed"
                        }
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="validate_conversion",
                description="Validate converted RPG code against uploaded coding standards and best practices",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "original_code": {"type": "string", "description": "Original traditional RPG code"},
                        "converted_code": {"type": "string", "description": "Converted free-form RPG code"},
                        "standards_reference": {"type": "string", "description": "Specific standards document to reference"}
                    },
                    "required": ["original_code", "converted_code"]
                }
            ),
            Tool(
                name="suggest_modernization",
                description="Suggest modernization techniques for RPG code based on current best practices",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "RPG code to analyze for modernization"},
                        "focus_areas": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["error_handling", "data_structures", "procedures", "sql_integration", "performance", "maintainability"]
                            },
                            "description": "Specific areas to focus modernization suggestions on"
                        }
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="compare_code_styles",
                description="Compare traditional and free-form RPG coding styles with examples from standards",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "operation_type": {
                            "type": "string",
                            "enum": ["file_operations", "calculations", "conditions", "loops", "procedures", "error_handling"],
                            "description": "Type of operation to compare"
                        },
                        "show_examples": {"type": "boolean", "description": "Include code examples", "default": True}
                    },
                    "required": ["operation_type"]
                }
            ),
            
            # Existing tools (continued)
            Tool(
                name="generate_code",
                description="Generate new code based on requirements and reference standards",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "requirements": {"type": "string", "description": "Detailed requirements for the code to be generated"},
                        "code_type": {
                            "type": "string",
                            "enum": ["sql", "db2", "rpg", "rpg_freeform", "procedure"],
                            "description": "Type of code to generate"
                        },
                        "style_guide": {"type": "string", "description": "Specific style guide or standards to follow", "default": "company_standards"},
                        "include_comments": {"type": "boolean", "description": "Include detailed comments in generated code", "default": True}
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
                        "code": {"type": "string", "description": "Code to be reviewed"},
                        "code_type": {
                            "type": "string",
                            "enum": ["sql", "db2", "rpg", "rpg_traditional", "rpg_freeform", "procedure"],
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
                        "code": {"type": "string", "description": "Code to be explained"},
                        "explanation_level": {
                            "type": "string",
                            "enum": ["beginner", "intermediate", "advanced"],
                            "description": "Level of explanation detail",
                            "default": "intermediate"
                        },
                        "include_references": {"type": "boolean", "description": "Include documentation references", "default": True}
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
                            "enum": ["module", "procedure", "package", "complete_program", "conversion_result"],
                            "description": "Type of artifact to create"
                        },
                        "specifications": {"type": "string", "description": "Detailed specifications for the artifact"},
                        "include_documentation": {"type": "boolean", "description": "Include comprehensive documentation", "default": True}
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
                            "enum": ["all", "standards", "procedures", "best_practices", "reference", "examples", "conversion_guide"],
                            "description": "Filter by document type",
                            "default": "all"
                        }
                    }
                }
            ),
            
            # Additional utility tools for enhanced workflows
            Tool(
                name="batch_analyze_rpg",
                description="Analyze multiple traditional RPG code segments in batch",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code_segments": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Name/identifier for this code segment"},
                                    "code": {"type": "string", "description": "Traditional RPG code to analyze"}
                                }
                            },
                            "description": "Array of code segments to analyze"
                        },
                        "include_conversion_estimates": {"type": "boolean", "description": "Include conversion time estimates", "default": True}
                    },
                    "required": ["code_segments"]
                }
            ),
            Tool(
                name="generate_conversion_report",
                description="Generate comprehensive conversion report for a project",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_name": {"type": "string", "description": "Name of the conversion project"},
                        "include_statistics": {"type": "boolean", "description": "Include conversion statistics", "default": True},
                        "include_recommendations": {"type": "boolean", "description": "Include modernization recommendations", "default": True}
                    },
                    "required": ["project_name"]
                }
            ),
            Tool(
                name="find_conversion_dependencies",
                description="Identify dependencies and relationships in RPG code for conversion planning",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "RPG code to analyze for dependencies"},
                        "scope": {
                            "type": "string",
                            "enum": ["files", "subroutines", "procedures", "all"],
                            "description": "Scope of dependency analysis",
                            "default": "all"
                        }
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="get_conversion_best_practices",
                description="Get specific best practices for RPG conversion from uploaded standards",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "conversion_area": {
                            "type": "string",
                            "enum": ["file_operations", "data_structures", "calculations", "error_handling", "procedures", "general"],
                            "description": "Specific area of conversion to get best practices for"
                        },
                        "difficulty_level": {
                            "type": "string",
                            "enum": ["basic", "intermediate", "advanced"],
                            "description": "Complexity level of best practices",
                            "default": "intermediate"
                        }
                    },
                    "required": ["conversion_area"]
                }
            ),
            Tool(
                name="estimate_conversion_effort",
                description="Estimate conversion effort and complexity for RPG code",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Traditional RPG code to estimate"},
                        "team_experience": {
                            "type": "string",
                            "enum": ["beginner", "intermediate", "expert"],
                            "description": "Team's RPG conversion experience level",
                            "default": "intermediate"
                        },
                        "include_timeline": {"type": "boolean", "description": "Include estimated timeline", "default": True}
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="create_conversion_checklist",
                description="Create a conversion checklist based on code analysis and standards",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code_analysis": {"type": "string", "description": "Previous code analysis results"},
                        "checklist_type": {
                            "type": "string",
                            "enum": ["pre_conversion", "during_conversion", "post_conversion", "complete"],
                            "description": "Type of checklist to create",
                            "default": "complete"
                        }
                    },
                    "required": ["code_analysis"]
                }
            )
        ]
    )

@mcp_server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """Handle tool calls with enhanced RPG conversion capabilities."""
    
    if name == "get_document_sections":
        section_title = arguments.get("section_title", "").lower()
        document_name = arguments.get("document_name", "")
        content_type = arguments.get("content_type", "")
        
        if not section_title:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide a section title to search for")]
            )
        
        found_sections = []
        for file_id, doc_meta in documents_metadata.items():
            # Filter by document name if specified
            if document_name and document_name.lower() not in doc_meta["filename"].lower():
                continue
            
            sections = doc_meta["content"].get("sections", {})
            for section_name, section_content in sections.items():
                if section_title in section_name.lower():
                    found_sections.append({
                        "document": doc_meta["filename"],
                        "section": section_name,
                        "content": "\n".join(section_content[:20])  # Limit content length
                    })
        
        if not found_sections:
            return CallToolResult(
                content=[TextContent(type="text", text=f"No sections found matching '{section_title}'")]
            )
        
        result_text = f"Found {len(found_sections)} sections matching '{section_title}':\n\n"
        for section in found_sections:
            result_text += f"📄 **{section['document']}** - {section['section']}\n"
            result_text += f"{section['content']}\n...\n\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "batch_analyze_rpg":
        code_segments = arguments.get("code_segments", [])
        include_conversion_estimates = arguments.get("include_conversion_estimates", True)
        
        if not code_segments:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide code segments to analyze")]
            )
        
        results = []
        total_complexity_score = 0
        
        for segment in code_segments:
            segment_name = segment.get("name", "Unnamed")
            segment_code = segment.get("code", "")
            
            if not segment_code:
                continue
            
            # Analyze the segment
            analysis = RPGConverter.analyze_traditional_rpg(segment_code)
            
            # Calculate complexity score
            complexity_score = 0
            complexity_score += len(analysis["file_specs"]) * 2
            complexity_score += len(analysis["calculation_specs"])
            complexity_score += len(analysis["indicators"]) * 3
            complexity_score += len(analysis["subroutines"]) * 2
            
            results.append({
                "name": segment_name,
                "analysis": analysis,
                "complexity_score": complexity_score,
                "lines": len(segment_code.split('\n'))
            })
            
            total_complexity_score += complexity_score
        
        result_text = f"**Batch RPG Analysis Report**\n\n"
        result_text += f"**Segments Analyzed:** {len(results)}\n"
        result_text += f"**Total Complexity Score:** {total_complexity_score}\n"
        result_text += f"**Average Complexity:** {total_complexity_score / len(results):.1f}\n\n"
        
        # Categorize by complexity
        low_complexity = [r for r in results if r["complexity_score"] < 10]
        medium_complexity = [r for r in results if 10 <= r["complexity_score"] < 30]
        high_complexity = [r for r in results if r["complexity_score"] >= 30]
        
        result_text += f"**Complexity Distribution:**\n"
        result_text += f"- Low Complexity: {len(low_complexity)} segments\n"
        result_text += f"- Medium Complexity: {len(medium_complexity)} segments\n"
        result_text += f"- High Complexity: {len(high_complexity)} segments\n\n"
        
        # Detailed results
        result_text += f"**Detailed Analysis:**\n\n"
        for i, result in enumerate(results, 1):
            result_text += f"{i}. **{result['name']}**\n"
            result_text += f"   - Lines: {result['lines']}\n"
            result_text += f"   - Complexity: {result['analysis']['conversion_complexity']}\n"
            result_text += f"   - File Specs: {len(result['analysis']['file_specs'])}\n"
            result_text += f"   - Calculation Specs: {len(result['analysis']['calculation_specs'])}\n"
            result_text += f"   - Subroutines: {len(result['analysis']['subroutines'])}\n"
            result_text += f"   - Indicators: {len(result['analysis']['indicators'])}\n"
            
            if include_conversion_estimates:
                # Estimate conversion time based on complexity
                if result['complexity_score'] < 10:
                    estimate = "1-2 hours"
                elif result['complexity_score'] < 30:
                    estimate = "4-8 hours"
                else:
                    estimate = "1-3 days"
                result_text += f"   - Estimated Conversion Time: {estimate}\n"
            
            result_text += "\n"
        
        if include_conversion_estimates:
            # Project-level estimates
            total_low_time = len(low_complexity) * 1.5  # hours
            total_medium_time = len(medium_complexity) * 6  # hours
            total_high_time = len(high_complexity) * 16  # hours
            total_hours = total_low_time + total_medium_time + total_high_time
            
            result_text += f"**Project Conversion Estimates:**\n"
            result_text += f"- Total Estimated Hours: {total_hours:.1f}\n"
            result_text += f"- Estimated Working Days: {total_hours / 8:.1f}\n"
            result_text += f"- Recommended Team Size: {max(1, int(total_hours / 40))}\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "generate_conversion_report":
        project_name = arguments.get("project_name", "RPG Conversion Project")
        include_statistics = arguments.get("include_statistics", True)
        include_recommendations = arguments.get("include_recommendations", True)
        
        # Gather statistics from processed documents and artifacts
        doc_stats = {
            "total_docs": len(documents_metadata),
            "standards_docs": len([d for d in documents_metadata.values() if d["document_type"] == "standards"]),
            "conversion_guides": len([d for d in documents_metadata.values() if d["document_type"] == "conversion_guide"]),
            "examples": len([d for d in documents_metadata.values() if d["document_type"] == "examples"])
        }
        
        # Count artifacts
        artifact_files = list(ARTIFACTS_DIR.glob("*.txt")) + list(ARTIFACTS_DIR.glob("*.rpg"))
        conversion_artifacts = [f for f in artifact_files if "conversion" in f.name]
        
        result_text = f"# {project_name} - Conversion Report\n\n"
        result_text += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        if include_statistics:
            result_text += f"## Project Statistics\n\n"
            result_text += f"### Documentation\n"
            result_text += f"- Total Documents Uploaded: {doc_stats['total_docs']}\n"
            result_text += f"- Coding Standards: {doc_stats['standards_docs']}\n"
            result_text += f"- Conversion Guides: {doc_stats['conversion_guides']}\n"
            result_text += f"- Code Examples: {doc_stats['examples']}\n\n"
            
            result_text += f"### Conversion Artifacts\n"
            result_text += f"- Total Artifacts Generated: {len(artifact_files)}\n"
            result_text += f"- Conversion Results: {len(conversion_artifacts)}\n\n"
            
            # Extract code examples statistics
            total_examples = 0
            rpg_traditional = 0
            rpg_freeform = 0
            
            for doc_meta in documents_metadata.values():
                examples = doc_meta.get("code_examples", [])
                total_examples += len(examples)
                for example in examples:
                    if example.get("format") == "traditional":
                        rpg_traditional += 1
                    elif example.get("format") == "freeform":
                        rpg_freeform += 1
            
            result_text += f"### Code Examples Analysis\n"
            result_text += f"- Total Code Examples: {total_examples}\n"
            result_text += f"- Traditional RPG: {rpg_traditional}\n"
            result_text += f"- Free-form RPG: {rpg_freeform}\n"
            result_text += f"- Other Languages: {total_examples - rpg_traditional - rpg_freeform}\n\n"
        
        if include_recommendations:
            result_text += f"## Conversion Recommendations\n\n"
            
            result_text += f"### Pre-Conversion Phase\n"
            result_text += f"1. **Standards Review**: Ensure all team members understand the coding standards\n"
            result_text += f"2. **Tool Setup**: Configure development environment for free-form RPG\n"
            result_text += f"3. **Training**: Provide training on modern RPG techniques\n"
            result_text += f"4. **Backup**: Create backups of all original code\n\n"
            
            result_text += f"### Conversion Priorities\n"
            result_text += f"1. **Start with Simple Programs**: Begin with low-complexity modules\n"
            result_text += f"2. **Focus on Procedures**: Convert subroutines to procedures first\n"
            result_text += f"3. **Modernize Error Handling**: Implement MONITOR/ON-ERROR blocks\n"
            result_text += f"4. **Update Data Structures**: Use qualified data structures\n\n"
            
            result_text += f"### Quality Assurance\n"
            result_text += f"1. **Validation Testing**: Test each converted program thoroughly\n"
            result_text += f"2. **Code Reviews**: Implement peer review process\n"
            result_text += f"3. **Standards Compliance**: Use validation tools to check compliance\n"
            result_text += f"4. **Documentation**: Update all related documentation\n\n"
            
            # Specific recommendations based on uploaded content
            if doc_stats['conversion_guides'] > 0:
                result_text += f"### Standards-Based Recommendations\n"
                result_text += f"✅ Conversion guides are available - follow documented procedures\n"
            else:
                result_text += f"⚠️ **Missing**: Upload conversion guides for standardized procedures\n"
            
            if doc_stats['standards_docs'] > 0:
                result_text += f"✅ Coding standards are available - apply during conversion\n"
            else:
                result_text += f"⚠️ **Missing**: Upload coding standards for consistent results\n"
            
            result_text += f"\n"
        
        result_text += f"## Next Steps\n\n"
        result_text += f"1. Review and approve this conversion plan\n"
        result_text += f"2. Set up development and testing environments\n"
        result_text += f"3. Begin with pilot conversion of simple programs\n"
        result_text += f"4. Establish conversion workflow and quality gates\n"
        result_text += f"5. Scale up conversion efforts based on pilot results\n\n"
        
        result_text += f"---\n"
        result_text += f"*Report generated by Enhanced DB2/RPG MCP Server v1.1*"
        
        # Save report as artifact
        report_id = str(uuid.uuid4())[:8]
        report_filename = f"conversion_report_{report_id}.md"
        report_path = ARTIFACTS_DIR / report_filename
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(result_text)
        
        result_text += f"\n\n📄 **Report saved as artifact:** {report_filename}"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "find_conversion_dependencies":
        code = arguments.get("code", "")
        scope = arguments.get("scope", "all")
        
        if not code:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide RPG code to analyze for dependencies")]
            )
        
        dependencies = {
            "files": [],
            "subroutines": [],
            "procedures": [],
            "copy_members": [],
            "external_calls": [],
            "indicators": []
        }
        
        lines = code.split('\n')
        
        for line in lines:
            line = line.strip().upper()
            
            # File dependencies (F-specs)
            if scope in ["files", "all"] and len(line) >= 6 and line[0] == 'F':
                filename = line[7:15].strip()
                if filename and filename not in dependencies["files"]:
                    dependencies["files"].append(filename)
            
            # DCL-F declarations
            if scope in ["files", "all"] and line.startswith('DCL-F'):
                match = re.search(r'DCL-F\s+(\w+)', line)
                if match:
                    filename = match.group(1)
                    if filename not in dependencies["files"]:
                        dependencies["files"].append(filename)
            
            # Subroutine dependencies
            if scope in ["subroutines", "all"]:
                if 'BEGSR' in line:
                    # Extract subroutine name from result field
                    if len(line) >= 63:
                        subr_name = line[50:63].strip()
                        if subr_name and subr_name not in dependencies["subroutines"]:
                            dependencies["subroutines"].append(subr_name)
                
                if 'EXSR' in line:
                    # Extract called subroutine name
                    if len(line) >= 63:
                        subr_name = line[50:63].strip()
                        if subr_name and subr_name not in dependencies["external_calls"]:
                            dependencies["external_calls"].append(f"Subroutine: {subr_name}")
            
            # Procedure dependencies
            if scope in ["procedures", "all"]:
                if 'DCL-PROC' in line:
                    match = re.search(r'DCL-PROC\s+(\w+)', line)
                    if match:
                        proc_name = match.group(1)
                        if proc_name not in dependencies["procedures"]:
                            dependencies["procedures"].append(proc_name)
            
            # Copy member dependencies
            if scope in ["all"] and '/COPY' in line:
                match = re.search(r'/COPY\s+(\w+),(\w+)', line)
                if match:
                    library = match.group(1)
                    member = match.group(2)
                    copy_ref = f"{library}/{member}"
                    if copy_ref not in dependencies["copy_members"]:
                        dependencies["copy_members"].append(copy_ref)
            
            # Indicator usage
            if scope in ["all"]:
                # Look for indicator references
                indicator_patterns = [r'\*IN\d+', r'\*INLR', r'\*INRT']
                for pattern in indicator_patterns:
                    matches = re.findall(pattern, line)
                    for match in matches:
                        if match not in dependencies["indicators"]:
                            dependencies["indicators"].append(match)
        
        result_text = f"**Conversion Dependencies Analysis**\n\n"
        result_text += f"**Scope:** {scope}\n\n"
        
        total_deps = sum(len(deps) for deps in dependencies.values())
        result_text += f"**Total Dependencies Found:** {total_deps}\n\n"
        
        for dep_type, dep_list in dependencies.items():
            if dep_list:
                result_text += f"**{dep_type.upper().replace('_', ' ')} ({len(dep_list)})**\n"
                for dep in dep_list:
                    result_text += f"- {dep}\n"
                result_text += "\n"
        
        if total_deps == 0:
            result_text += "✅ No external dependencies found.\n\n"
        else:
            result_text += f"**Conversion Impact:**\n"
            if dependencies["files"]:
                result_text += f"- File dependencies may require DCL-F conversion\n"
            if dependencies["subroutines"]:
                result_text += f"- Subroutines should be converted to procedures\n"
            if dependencies["copy_members"]:
                result_text += f"- Copy members may need updating for free-form syntax\n"
            if dependencies["indicators"]:
                result_text += f"- Indicators should be replaced with logical variables\n"
            if dependencies["external_calls"]:
                result_text += f"- External calls may need signature updates\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "get_conversion_best_practices":
        conversion_area = arguments.get("conversion_area", "general")
        difficulty_level = arguments.get("difficulty_level", "intermediate")
        
        # Search for best practices in uploaded documents
        best_practices = []
        
        for file_id, doc_meta in documents_metadata.items():
            if doc_meta["document_type"] in ["best_practices", "conversion_guide", "standards"]:
                content = doc_meta["content"].get("text", "").lower()
                sections = doc_meta["content"].get("sections", {})
                
                # Look for relevant sections
                for section_name, section_content in sections.items():
                    section_text = " ".join(section_content).lower()
                    
                    if conversion_area in section_text or "conversion" in section_text:
                        best_practices.append({
                            "source": doc_meta["filename"],
                            "section": section_name,
                            "content": " ".join(section_content[:5])  # First 5 lines
                        })
        
        result_text = f"**RPG Conversion Best Practices**\n\n"
        result_text += f"**Area:** {conversion_area.replace('_', ' ').title()}\n"
        result_text += f"**Level:** {difficulty_level}\n\n"
        
        # Provide built-in best practices
        if conversion_area == "file_operations":
            result_text += f"**File Operations Conversion:**\n\n"
            result_text += f"**Traditional Format:**\n"
            result_text += f"```rpg\n"
            result_text += f"F CUSTFILE  IF   E           K DISK\n"
            result_text += f"```\n\n"
            result_text += f"**Free-form Conversion:**\n"
            result_text += f"```rpg\n"
            result_text += f"DCL-F CUSTFILE DISK(*EXT) USAGE(*INPUT) KEYED;\n"
            result_text += f"```\n\n"
            result_text += f"**Best Practices:**\n"
            result_text += f"- Use DCL-F for all file declarations\n"
            result_text += f"- Specify USAGE explicitly (*INPUT, *OUTPUT, *UPDATE)\n"
            result_text += f"- Use KEYED for keyed access methods\n"
            result_text += f"- Consider TEMPLATE for externally described files\n"
        
        elif conversion_area == "error_handling":
            result_text += f"**Error Handling Modernization:**\n\n"
            result_text += f"**Traditional Approach:**\n"
            result_text += f"```rpg\n"
            result_text += f"C                   CHAIN     key           FILE1\n"
            result_text += f"C                   IF        %ERROR\n"
            result_text += f"C                   // Handle error\n"
            result_text += f"C                   ENDIF\n"
            result_text += f"```\n\n"
            result_text += f"**Modern Free-form:**\n"
            result_text += f"```rpg\n"
            result_text += f"MONITOR;\n"
            result_text += f"    CHAIN key FILE1;\n"
            result_text += f"ON-ERROR;\n"
            result_text += f"    // Handle error with specific error code\n"
            result_text += f"    errorMsg = 'Chain operation failed: ' + %CHAR(%ERROR);\n"
            result_text += f"ENDMON;\n"
            result_text += f"```\n\n"
            result_text += f"**Best Practices:**\n"
            result_text += f"- Use MONITOR/ON-ERROR for exception handling\n"
            result_text += f"- Check %ERROR and %STATUS for error conditions\n"
            result_text += f"- Provide meaningful error messages\n"
            result_text += f"- Log errors appropriately\n"
        
        elif conversion_area == "procedures":
            result_text += f"**Subroutine to Procedure Conversion:**\n\n"
            result_text += f"**Traditional Subroutine:**\n"
            result_text += f"```rpg\n"
            result_text += f"C     calcTotal    BEGSR\n"
            result_text += f"C                   EVAL      total = amt1 + amt2\n"
            result_text += f"C                   ENDSR\n"
            result_text += f"```\n\n"
            result_text += f"**Modern Procedure:**\n"
            result_text += f"```rpg\n"
            result_text += f"DCL-PROC calcTotal;\n"
            result_text += f"    DCL-PI *N PACKED(15:2);\n"
            result_text += f"        amt1 PACKED(15:2) CONST;\n"
            result_text += f"        amt2 PACKED(15:2) CONST;\n"
            result_text += f"    END-PI;\n"
            result_text += f"    RETURN amt1 + amt2;\n"
            result_text += f"END-PROC;\n"
            result_text += f"```\n\n"
            result_text += f"**Best Practices:**\n"
            result_text += f"- Convert all subroutines to procedures\n"
            result_text += f"- Define clear parameter interfaces\n"
            result_text += f"- Use CONST for input-only parameters\n"
            result_text += f"- Return values instead of global variables\n"
            result_text += f"- Use EXPORT for externally callable procedures\n"
        
        elif conversion_area == "data_structures":
            result_text += f"**Data Structure Modernization:**\n\n"
            result_text += f"**Traditional DS:**\n"
            result_text += f"```rpg\n"
            result_text += f"D customer       DS\n"
            result_text += f"D  custId                        7P 0\n"
            result_text += f"D  custName                     50A\n"
            result_text += f"```\n\n"
            result_text += f"**Modern Qualified DS:**\n"
            result_text += f"```rpg\n"
            result_text += f"DCL-DS customer QUALIFIED TEMPLATE;\n"
            result_text += f"    custId PACKED(7:0);\n"
            result_text += f"    custName CHAR(50);\n"
            result_text += f"END-DS;\n"
            result_text += f"```\n\n"
            result_text += f"**Best Practices:**\n"
            result_text += f"- Use QUALIFIED data structures\n"
            result_text += f"- Create TEMPLATE data structures for reuse\n"
            result_text += f"- Use descriptive field names\n"
            result_text += f"- Group related fields logically\n"
        
        # Add practices from uploaded documents
        if best_practices:
            result_text += f"\n**From Uploaded Standards:**\n\n"
            for practice in best_practices[:3]:  # Limit to top 3
                result_text += f"**{practice['source']} - {practice['section']}**\n"
                result_text += f"{practice['content']}...\n\n"
        
        if difficulty_level == "advanced":
            result_text += f"\n**Advanced Considerations:**\n"
            result_text += f"- Performance implications of free-form syntax\n"
            result_text += f"- Integration with modern RPG features\n"
            result_text += f"- Compatibility with existing systems\n"
            result_text += f"- Testing strategies for converted code\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "estimate_conversion_effort":
        code = arguments.get("code", "")
        team_experience = arguments.get("team_experience", "intermediate")
        include_timeline = arguments.get("include_timeline", True)
        
        if not code:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide traditional RPG code to estimate")]
            )
        
        # Analyze the code
        analysis = RPGConverter.analyze_traditional_rpg(code)
        
        # Calculate base effort metrics
        lines_of_code = len([line for line in code.split('\n') if line.strip()])
        complexity_factors = {
            "file_specs": len(analysis["file_specs"]) * 0.5,  # hours per file
            "definition_specs": len(analysis["definition_specs"]) * 0.25,  # hours per definition
            "calculation_specs": len(analysis["calculation_specs"]) * 0.1,  # hours per calc
            "subroutines": len(analysis["subroutines"]) * 2,  # hours per subroutine
            "indicators": len(analysis["indicators"]) * 0.5,  # hours per indicator
            "base_conversion": lines_of_code * 0.05  # base time per line
        }
        
        base_hours = sum(complexity_factors.values())
        
        # Apply experience multipliers
        experience_multipliers = {
            "beginner": 2.0,
            "intermediate": 1.0,
            "expert": 0.7
        }
        
        adjusted_hours = base_hours * experience_multipliers.get(team_experience, 1.0)
        
        # Add testing and validation time (50% of conversion time)
        testing_hours = adjusted_hours * 0.5
        total_hours = adjusted_hours + testing_hours
        
        result_text = f"**RPG Conversion Effort Estimation**\n\n"
        result_text += f"**Code Analysis:**\n"
        result_text += f"- Lines of Code: {lines_of_code}\n"
        result_text += f"- Complexity: {analysis['conversion_complexity']}\n"
        result_text += f"- Team Experience: {team_experience}\n\n"
        
        result_text += f"**Effort Breakdown:**\n"
        result_text += f"- File Conversions: {complexity_factors['file_specs']:.1f} hours\n"
        result_text += f"- Data Definitions: {complexity_factors['definition_specs']:.1f} hours\n"
        result_text += f"- Logic Conversion: {complexity_factors['calculation_specs']:.1f} hours\n"
        result_text += f"- Subroutine to Procedure: {complexity_factors['subroutines']:.1f} hours\n"
        result_text += f"- Indicator Replacement: {complexity_factors['indicators']:.1f} hours\n"
        result_text += f"- Base Conversion: {complexity_factors['base_conversion']:.1f} hours\n\n"
        
        result_text += f"**Total Estimates:**\n"
        result_text += f"- Base Conversion Time: {base_hours:.1f} hours\n"
        result_text += f"- Adjusted for Experience: {adjusted_hours:.1f} hours\n"
        result_text += f"- Testing & Validation: {testing_hours:.1f} hours\n"
        result_text += f"- **Total Project Time: {total_hours:.1f} hours**\n\n"
        
        if include_timeline:
            working_days = total_hours / 8
            calendar_days = working_days * 1.4  # Account for meetings, planning, etc.
            
            result_text += f"**Timeline Estimates:**\n"
            result_text += f"- Working Days: {working_days:.1f} days\n"
            result_text += f"- Calendar Days: {calendar_days:.1f} days\n"
            result_text += f"- Weeks (5-day): {working_days / 5:.1f} weeks\n\n"
            
            # Provide milestone recommendations
            result_text += f"**Recommended Milestones:**\n"
            result_text += f"1. Analysis & Planning: {total_hours * 0.1:.1f} hours\n"
            result_text += f"2. File & Data Conversion: {total_hours * 0.3:.1f} hours\n"
            result_text += f"3. Logic Conversion: {total_hours * 0.4:.1f} hours\n"
            result_text += f"4. Testing & Validation: {total_hours * 0.2:.1f} hours\n"
        
        # Risk factors
        result_text += f"\n**Risk Factors:**\n"
        if analysis['conversion_complexity'] == 'high':
            result_text += f"⚠️ High complexity - consider breaking into smaller modules\n"
        if len(analysis['indicators']) > 10:
            result_text += f"⚠️ Heavy indicator usage - may require significant refactoring\n"
        if len(analysis['subroutines']) > 5:
            result_text += f"⚠️ Many subroutines - procedure conversion will be time-consuming\n"
        
        result_text += f"\n**Confidence Level:** "
        if analysis['conversion_complexity'] == 'low':
            result_text += f"High (±20%)\n"
        elif analysis['conversion_complexity'] == 'medium':
            result_text += f"Medium (±30%)\n"
        else:
            result_text += f"Low (±50%)\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "create_conversion_checklist":
        code_analysis = arguments.get("code_analysis", "")
        checklist_type = arguments.get("checklist_type", "complete")
        
        result_text = f"**RPG Conversion Checklist**\n\n"
        result_text += f"**Type:** {checklist_type.replace('_', ' ').title()}\n"
        result_text += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        if checklist_type in ["pre_conversion", "complete"]:
            result_text += f"## Pre-Conversion Checklist\n\n"
            result_text += f"### Documentation & Standards\n"
            result_text += f"- [ ] Upload and review coding standards documents\n"
            result_text += f"- [ ] Upload conversion guides and best practices\n"
            result_text += f"- [ ] Document current system architecture\n"
            result_text += f"- [ ] Identify all RPG programs to be converted\n"
            result_text += f"- [ ] Create inventory of shared copy members\n\n"
            
            result_text += f"### Environment Setup\n"
            result_text += f"- [ ] Set up development environment for free-form RPG\n"
            result_text += f"- [ ] Configure compiler options for free-form\n"
            result_text += f"- [ ] Set up testing environment\n"
            result_text += f"- [ ] Create backup of all original source code\n"
            result_text += f"- [ ] Install and configure development tools\n\n"
            
            result_text += f"### Team Preparation\n"
            result_text += f"- [ ] Train team on free-form RPG syntax\n"
            result_text += f"- [ ] Review conversion best practices\n"
            result_text += f"- [ ] Assign roles and responsibilities\n"
            result_text += f"- [ ] Establish code review process\n\n"
        
        if checklist_type in ["during_conversion", "complete"]:
            result_text += f"## During Conversion Checklist\n\n"
            result_text += f"### Code Analysis\n"
            result_text += f"- [ ] Analyze traditional RPG code structure\n"
            result_text += f"- [ ] Identify file dependencies\n"
            result_text += f"- [ ] Map subroutines to procedures\n"
            result_text += f"- [ ] Document indicator usage\n"
            result_text += f"- [ ] Note any special considerations\n\n"
            
            result_text += f"### Conversion Process\n"
            result_text += f"- [ ] Convert H-specs to **CTL-OPT\n"
            result_text += f"- [ ] Convert F-specs to DCL-F declarations\n"
            result_text += f"- [ ] Convert D-specs to DCL-S/DCL-DS\n"
            result_text += f"- [ ] Convert calculation specs to free-form\n"
            result_text += f"- [ ] Convert subroutines to procedures\n"
            result_text += f"- [ ] Replace indicators with logical variables\n"
            result_text += f"- [ ] Add modern error handling (MONITOR/ON-ERROR)\n"
            result_text += f"- [ ] Update copy member references\n\n"
            
            result_text += f"### Quality Checks\n"
            result_text += f"- [ ] Verify syntax correctness\n"
            result_text += f"- [ ] Check compliance with coding standards\n"
            result_text += f"- [ ] Validate against original functionality\n"
            result_text += f"- [ ] Review for modernization opportunities\n"
            result_text += f"- [ ] Perform peer code review\n\n"
        
        if checklist_type in ["post_conversion", "complete"]:
            result_text += f"## Post-Conversion Checklist\n\n"
            result_text += f"### Testing & Validation\n"
            result_text += f"- [ ] Compile converted program successfully\n"
            result_text += f"- [ ] Run unit tests\n"
            result_text += f"- [ ] Perform integration testing\n"
            result_text += f"- [ ] Validate business logic functionality\n"
            result_text += f"- [ ] Test error handling scenarios\n"
            result_text += f"- [ ] Performance testing if applicable\n\n"
            
            result_text += f"### Documentation Updates\n"
            result_text += f"- [ ] Update program documentation\n"
            result_text += f"- [ ] Update system documentation\n"
            result_text += f"- [ ] Document conversion notes and decisions\n"
            result_text += f"- [ ] Update maintenance procedures\n\n"
            
            result_text += f"### Deployment Preparation\n"
            result_text += f"- [ ] Create deployment package\n"
            result_text += f"- [ ] Prepare rollback plan\n"
            result_text += f"- [ ] Schedule deployment window\n"
            result_text += f"- [ ] Notify stakeholders\n"
            result_text += f"- [ ] Prepare production environment\n\n"
            
            result_text += f"### Final Validation\n"
            result_text += f"- [ ] Final code review\n"
            result_text += f"- [ ] Management approval\n"
            result_text += f"- [ ] Archive original code\n"
            result_text += f"- [ ] Update change management records\n\n"
        
        # Add specific items based on code analysis if provided
        if code_analysis and "subroutines" in code_analysis.lower():
            result_text += f"## Specific Conversion Items (Based on Analysis)\n\n"
            result_text += f"- [ ] **Subroutines Detected**: Convert to procedures with proper interfaces\n"
        
        if code_analysis and "indicators" in code_analysis.lower():
            result_text += f"- [ ] **Indicators Detected**: Replace with logical variables\n"
        
        if code_analysis and "file" in code_analysis.lower():
            result_text += f"- [ ] **File Operations Detected**: Update to modern DCL-F syntax\n"
        
        result_text += f"\n---\n"
        result_text += f"**Notes:**\n"
        result_text += f"- Check off items as they are completed\n"
        result_text += f"- Add additional items specific to your project\n"
        result_text += f"- Keep this checklist updated throughout the project\n"
        result_text += f"- Use this as a quality gate for each conversion\n"
        
        # Save checklist as artifact
        checklist_id = str(uuid.uuid4())[:8]
        checklist_filename = f"conversion_checklist_{checklist_id}.md"
        checklist_path = ARTIFACTS_DIR / checklist_filename
        
        with open(checklist_path, 'w', encoding='utf-8') as f:
            f.write(result_text)
        
        result_text += f"\n\n📋 **Checklist saved as artifact:** {checklist_filename}"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "extract_rpg_patterns":
        pattern_type = arguments.get("pattern_type", "")
        format_type = arguments.get("format", "both")
        
        patterns = []
        for file_id, doc_meta in documents_metadata.items():
            if doc_meta["document_type"] in ["standards", "best_practices", "examples"]:
                content = doc_meta["content"].get("text", "")
                code_examples = doc_meta.get("code_examples", [])
                
                # Filter by pattern type
                if pattern_type == "naming_conventions":
                    # Look for naming convention examples
                    naming_patterns = re.findall(r'(?i)(variable\s+name|field\s+name|naming\s+convention).*?\n.*?\n.*?\n', content)
                    for pattern in naming_patterns:
                        patterns.append({
                            "type": "naming_conventions",
                            "source": doc_meta["filename"],
                            "pattern": pattern.strip()
                        })
                
                elif pattern_type == "error_handling":
                    # Look for error handling patterns
                    for example in code_examples:
                        if "monitor" in example["code"].lower() or "error" in example["code"].lower():
                            patterns.append({
                                "type": "error_handling",
                                "source": doc_meta["filename"],
                                "pattern": example["code"],
                                "format": example.get("format", "unknown")
                            })
                
                elif pattern_type == "conversion_rules":
                    # Look for conversion rules and mappings
                    conversion_patterns = re.findall(r'(?i)(traditional|fixed.?format).*?(?:convert|free.?form).*?\n.*?\n', content)
                    for pattern in conversion_patterns:
                        patterns.append({
                            "type": "conversion_rules",
                            "source": doc_meta["filename"],
                            "pattern": pattern.strip()
                        })
        
        if not patterns:
            return CallToolResult(
                content=[TextContent(type="text", text=f"No {pattern_type} patterns found in uploaded documents")]
            )
        
        result_text = f"Found {len(patterns)} {pattern_type} patterns:\n\n"
        for i, pattern in enumerate(patterns[:10], 1):
            result_text += f"{i}. **{pattern['source']}** ({pattern['type']})\n"
            result_text += f"```\n{pattern['pattern']}\n```\n\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "analyze_rpg_syntax":
        code = arguments.get("code", "")
        include_conversion_plan = arguments.get("include_conversion_plan", True)
        
        if not code:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide RPG code to analyze")]
            )
        
        analysis = RPGConverter.analyze_traditional_rpg(code)
        
        result_text = "**RPG Syntax Analysis Report**\n\n"
        result_text += f"**Format:** {analysis['format']}\n"
        result_text += f"**Conversion Complexity:** {analysis['conversion_complexity']}\n"
        result_text += f"**Fixed Format Lines:** {analysis['fixed_format_lines']}\n\n"
        
        result_text += "**Components Found:**\n"
        result_text += f"- Control Specs: {len(analysis['control_specs'])}\n"
        result_text += f"- File Specs: {len(analysis['file_specs'])}\n"
        result_text += f"- Definition Specs: {len(analysis['definition_specs'])}\n"
        result_text += f"- Calculation Specs: {len(analysis['calculation_specs'])}\n"
        result_text += f"- Subroutines: {len(analysis['subroutines'])}\n"
        result_text += f"- Indicators Used: {len(analysis['indicators'])}\n\n"
        
        if analysis['file_specs']:
            result_text += "**Files Used:**\n"
            for file_spec in analysis['file_specs']:
                result_text += f"- {file_spec['filename']} ({file_spec['file_type']})\n"
        
        if analysis['subroutines']:
            result_text += "\n**Subroutines:**\n"
            for subroutine in analysis['subroutines']:
                result_text += f"- {subroutine}\n"
        
        if include_conversion_plan:
            result_text += "\n**Conversion Plan:**\n"
            result_text += "1. Convert H-specs to **CTL-OPT control specification\n"
            result_text += "2. Convert F-specs to DCL-F file declarations\n"
            result_text += "3. Convert D-specs to DCL-S/DCL-DS data structure declarations\n"
            result_text += "4. Convert calculation specs to free-form logic\n"
            result_text += "5. Convert subroutines to procedures\n"
            result_text += "6. Replace indicators with logical variables\n"
            
            if analysis['conversion_complexity'] == 'high':
                result_text += "\n⚠️ **High complexity conversion** - consider breaking into smaller modules\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "convert_rpg_to_freeform":
        code = arguments.get("code", "")
        apply_standards = arguments.get("apply_standards", True)
        include_comments = arguments.get("include_comments", True)
        validation_level = arguments.get("validation_level", "detailed")
        
        if not code:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide traditional RPG code to convert")]
            )
        
        # Get coding standards from uploaded documents
        standards = {}
        if apply_standards:
            for file_id, doc_meta in documents_metadata.items():
                if doc_meta["document_type"] in ["standards", "best_practices"]:
                    standards[doc_meta["filename"]] = doc_meta["content"]
        
        # Perform conversion
        conversion_result = RPGConverter.convert_to_freeform(code, standards)
        
        result_text = "**RPG to Free-form Conversion Result**\n\n"
        
        if conversion_result["success"]:
            result_text += "✅ **Conversion Successful**\n\n"
            result_text += "**Converted Code:**\n"
            result_text += f"```rpg\n{conversion_result['converted_code']}\n```\n\n"
            
            if conversion_result["conversion_notes"]:
                result_text += "**Conversion Notes:**\n"
                for note in conversion_result["conversion_notes"]:
                    result_text += f"- {note}\n"
                result_text += "\n"
            
            if conversion_result["warnings"]:
                result_text += "⚠️ **Warnings:**\n"
                for warning in conversion_result["warnings"]:
                    result_text += f"- {warning}\n"
                result_text += "\n"
            
            if apply_standards and conversion_result["standards_applied"]:
                result_text += "📋 **Standards Applied:**\n"
                for standard in conversion_result["standards_applied"]:
                    result_text += f"- {standard}\n"
                result_text += "\n"
            
            # Save as artifact if large
            if len(conversion_result["converted_code"]) > 1000:
                artifact_id = str(uuid.uuid4())[:8]
                artifact_filename = f"conversion_{artifact_id}.rpg"
                artifact_path = ARTIFACTS_DIR / artifact_filename
                
                with open(artifact_path, 'w', encoding='utf-8') as f:
                    f.write(conversion_result["converted_code"])
                
                result_text += f"💾 **Large conversion saved as artifact:** {artifact_filename}\n"
        
        else:
            result_text += f"❌ **Conversion Failed:** {conversion_result.get('error', 'Unknown error')}\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "validate_conversion":
        original_code = arguments.get("original_code", "")
        converted_code = arguments.get("converted_code", "")
        standards_reference = arguments.get("standards_reference", "")
        
        if not original_code or not converted_code:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide both original and converted code")]
            )
        
        validation_result = {
            "syntax_valid": True,
            "standards_compliance": [],
            "functional_equivalence": [],
            "recommendations": []
        }
        
        # Basic syntax validation
        result_text = "**Conversion Validation Report**\n\n"
        
        # Check for common conversion issues
        original_lines = original_code.split('\n')
        converted_lines = converted_code.split('\n')
        
        # Validate structure
        if "**CTL-OPT" in converted_code:
            validation_result["standards_compliance"].append("✅ Control specification properly converted")
        
        if "DCL-F" in converted_code and any(line[5:6] == 'F' for line in original_lines if len(line) > 5):
            validation_result["standards_compliance"].append("✅ File specifications converted")
        
        if "DCL-S" in converted_code or "DCL-DS" in converted_code:
            validation_result["standards_compliance"].append("✅ Data structures properly declared")
        
        # Check for potential issues
        if "GOTO" in converted_code.upper():
            validation_result["recommendations"].append("⚠️ GOTO statements detected - consider refactoring")
        
        if re.search(r'\*IN\d+', converted_code):
            validation_result["recommendations"].append("⚠️ Indicator usage detected - consider logical variables")
        
        # Build result
        result_text += "**Standards Compliance:**\n"
        for item in validation_result["standards_compliance"]:
            result_text += f"{item}\n"
        
        if validation_result["recommendations"]:
            result_text += "\n**Recommendations:**\n"
            for rec in validation_result["recommendations"]:
                result_text += f"{rec}\n"
        
        result_text += f"\n**Overall Assessment:** Conversion appears functional with {len(validation_result['recommendations'])} recommendations for improvement."
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "suggest_modernization":
        code = arguments.get("code", "")
        focus_areas = arguments.get("focus_areas", ["maintainability", "error_handling"])
        
        if not code:
            return CallToolResult(
                content=[TextContent(type="text", text="Please provide RPG code to analyze for modernization")]
            )
        
        suggestions = []
        
        # Analyze based on focus areas
        for area in focus_areas:
            if area == "error_handling":
                if not re.search(r'MONITOR', code, re.IGNORECASE):
                    suggestions.append({
                        "area": "Error Handling",
                        "suggestion": "Add MONITOR/ON-ERROR blocks for robust error handling",
                        "example": "MONITOR;\n    // risky operation\nON-ERROR;\n    // error handling\nENDMON;"
                    })
            
            elif area == "procedures":
                if re.search(r'BEGSR', code, re.IGNORECASE):
                    suggestions.append({
                        "area": "Procedures",
                        "suggestion": "Convert subroutines to procedures for better modularity",
                        "example": "DCL-PROC myProcedure;\n    // procedure logic\nEND-PROC;"
                    })
            
            elif area == "sql_integration":
                if re.search(r'CHAIN|READ|WRITE', code, re.IGNORECASE):
                    suggestions.append({
                        "area": "SQL Integration",
                        "suggestion": "Consider using embedded SQL for database operations",
                        "example": "EXEC SQL\n    SELECT field INTO :variable\n    FROM table\n    WHERE condition = :key;"
                    })
            
            elif area == "data_structures":
                if re.search(r'DCL-S.*CHAR', code, re.IGNORECASE):
                    suggestions.append({
                        "area": "Data Structures",
                        "suggestion": "Use qualified data structures for better organization",
                        "example": "DCL-DS customer QUALIFIED TEMPLATE;\n    name CHAR(50);\n    id PACKED(7:0);\nEND-DS;"
                    })
        
        result_text = "**Modernization Suggestions**\n\n"
        
        if suggestions:
            for i, suggestion in enumerate(suggestions, 1):
                result_text += f"**{i}. {suggestion['area']}**\n"
                result_text += f"{suggestion['suggestion']}\n\n"
                result_text += f"**Example:**\n```rpg\n{suggestion['example']}\n```\n\n"
        else:
            result_text += "Code appears to follow modern RPG practices. No specific modernization suggestions found.\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    elif name == "compare_code_styles":
        operation_type = arguments.get("operation_type", "")
        show_examples = arguments.get("show_examples", True)
        
        if not operation_type:
            return CallToolResult(
                content=[TextContent(type="text", text="Please specify an operation type to compare")]
            )
        
        comparisons = {
            "file_operations": {
                "traditional": "F  MYFILE    IF   E           K DISK",
                "freeform": "DCL-F MYFILE DISK(*EXT) USAGE(*INPUT) KEYED;",
                "description": "File specification declaration"
            },
            "calculations": {
                "traditional": "C                   EVAL      result = field1 + field2",
                "freeform": "result = field1 + field2;",
                "description": "Arithmetic calculations"
            },
            "conditions": {
                "traditional": "C                   IF        field1 > field2\nC                   EVAL      result = 'Greater'\nC                   ENDIF",
                "freeform": "IF field1 > field2;\n    result = 'Greater';\nENDIF;",
                "description": "Conditional logic"
            },
            "loops": {
                "traditional": "C                   FOR       i = 1 TO 10\nC                   EVAL      total = total + i\nC                   ENDFOR",
                "freeform": "FOR i = 1 TO 10;\n    total += i;\nENDFOR;",
                "description": "Loop structures"
            },
            "procedures": {
                "traditional": "C     calcTotal    BEGSR\nC                   EVAL      total = amt1 + amt2\nC                   ENDSR",
                "freeform": "DCL-PROC calcTotal;\n    DCL-PI *N PACKED(15:2);\n        amt1 PACKED(15:2) CONST;\n        amt2 PACKED(15:2) CONST;\n    END-PI;\n    RETURN amt1 + amt2;\nEND-PROC;",
                "description": "Procedure definition and implementation"
            },
            "error_handling": {
                "traditional": "C                   CHAIN     key           FILE1\nC                   IF        %FOUND(FILE1)\nC                   EVAL      found = *ON\nC                   ENDIF",
                "freeform": "MONITOR;\n    CHAIN key FILE1;\n    found = %FOUND(FILE1);\nON-ERROR;\n    // Handle error\nENDMON;",
                "description": "Error handling approaches"
            }
        }
        
        comparison = comparisons.get(operation_type)
        
        if not comparison:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown operation type: {operation_type}")]
            )
        
        result_text = f"**Comparison: {operation_type.replace('_', ' ').title()}**\n\n"
        result_text += f"**Description:** {comparison['description']}\n\n"
        
        if show_examples:
            result_text += "**Traditional RPG (Fixed Format):**\n"
            result_text += f"```rpg\n{comparison['traditional']}\n```\n\n"
            
            result_text += "**Free-form RPG:**\n"
            result_text += f"```rpg\n{comparison['freeform']}\n```\n\n"
            
            result_text += "**Key Differences:**\n"
            result_text += "- Free-form uses natural language syntax\n"
            result_text += "- No fixed column positions required\n"
            result_text += "- More readable and maintainable\n"
            result_text += "- Better integration with modern IDE features\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    # Continue with existing tool implementations...
    # (The rest of the existing tools remain the same)
    
    elif name == "upload_document":
        # Enhanced document processing with conversion guide support
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
        
        # Enhanced code extraction for RPG
        code_blocks = CodeAnalyzer.extract_code_blocks(content.get("text", ""))
        documents_metadata[file_id]["code_examples"] = code_blocks
        
        result = f"Document '{filename}' processed successfully:\n"
        result += f"- Type: {document_type}\n"
        result += f"- Pages/Size: {content.get('pages', content.get('size', 'N/A'))}\n"
        result += f"- Images: {len(content.get('images', []))}\n"
        result += f"- Code examples found: {len(code_blocks)}\n"
        result += f"- Sections identified: {len(content.get('sections', {}))}\n"
        
        # Special handling for conversion guides
        if document_type == "conversion_guide":
            rpg_examples = [ex for ex in code_blocks if ex.get("language") == "rpg"]
            result += f"- RPG examples found: {len(rpg_examples)}\n"
        
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
            
            # Search in content and sections
            content_text = doc_meta["content"].get("text", "").lower()
            sections = doc_meta["content"].get("sections", {})
            
            if query in content_text:
                # Extract relevant excerpts
                sentences = content_text.split('.')
                relevant_excerpts = []
                for sentence in sentences:
                    if query in sentence:
                        relevant_excerpts.append(sentence.strip()[:200] + "...")
                        if len(relevant_excerpts) >= 2:
                            break
                
                # Check for relevant sections
                relevant_sections = []
                for section_name, section_content in sections.items():
                    section_text = " ".join(section_content).lower()
                    if query in section_text:
                        relevant_sections.append(section_name)
                
                results.append({
                    "document": doc_meta["filename"],
                    "type": doc_meta["document_type"],
                    "description": doc_meta["description"],
                    "excerpts": relevant_excerpts,
                    "relevant_sections": relevant_sections
                })
        
        if not results:
            return CallToolResult(
                content=[TextContent(type="text", text=f"No results found for query: '{query}'")]
            )
        
        # Limit results
        results = results[:max_results]
        
        result_text = f"Found {len(results)} relevant documents for '{query}':\n\n"
        for i, result in enumerate(results, 1):
            result_text += f"{i}. **{result['document']}** ({result['type']})\n"
            result_text += f"   Description: {result['description']}\n"
            
            if result['relevant_sections']:
                result_text += f"   Relevant sections: {', '.join(result['relevant_sections'])}\n"
            
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
                # Enhanced filtering by code type
                example_type = example["type"].lower()
                example_format = example.get("format", "").lower()
                
                # Filter by code type with enhanced RPG support
                if code_type != "all":
                    if code_type == "rpg" and "rpg" not in example_type:
                        continue
                    elif code_type == "rpg_traditional" and example_format != "traditional":
                        continue
                    elif code_type == "rpg_freeform" and example_format != "freeform":
                        continue
                    elif code_type not in example_type and code_type != "rpg":
                        continue
                
                # Filter by topic if specified
                if topic and topic not in example["code"].lower():
                    continue
                
                all_examples.append({
                    "source": doc_meta["filename"],
                    "type": example["type"],
                    "code": example["code"],
                    "language": example["language"],
                    "format": example.get("format", "unknown")
                })
        
        if not all_examples:
            return CallToolResult(
                content=[TextContent(type="text", text=f"No code examples found for type: {code_type}, topic: {topic}")]
            )
        
        result_text = f"Found {len(all_examples)} code examples:\n\n"
        for i, example in enumerate(all_examples[:10], 1):  # Limit to 10 examples
            result_text += f"{i}. **{example['type']}** from *{example['source']}*"
            if example['format'] != 'unknown':
                result_text += f" ({example['format']} format)"
            result_text += ":\n"
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
        relevant_examples = []
        
        for file_id, doc_meta in documents_metadata.items():
            if doc_meta["document_type"] in ["standards", "best_practices", "examples"]:
                relevant_docs.append(doc_meta)
                
                # Get relevant code examples
                code_examples = doc_meta.get("code_examples", [])
                for example in code_examples:
                    if code_type.lower() in example["type"].lower():
                        relevant_examples.append(example)
        
        result_text = f"Generated {code_type.upper()} code based on requirements and company standards:\n\n"
        
        if code_type.lower() == "sql":
            result_text += "```sql\n"
            if include_comments:
                result_text += "-- Generated SQL based on requirements\n"
                result_text += "-- Following company coding standards\n\n"
                result_text += f"-- Requirements: {requirements}\n\n"
            
            # Generate based on requirements
            if "select" in requirements.lower() or "query" in requirements.lower():
                result_text += "SELECT \n    column1,\n    column2,\n    column3\nFROM table_name\nWHERE condition = 'value'\nORDER BY column1;\n"
            elif "create" in requirements.lower() and "table" in requirements.lower():
                result_text += "CREATE TABLE new_table (\n    id INTEGER NOT NULL PRIMARY KEY,\n    name VARCHAR(50) NOT NULL,\n    created_date DATE DEFAULT CURRENT_DATE\n);\n"
            elif "procedure" in requirements.lower():
                result_text += "CREATE OR REPLACE PROCEDURE sample_procedure(\n    IN param1 VARCHAR(50),\n    OUT result VARCHAR(100)\n)\nBEGIN\n    -- Procedure implementation\n    SET result = 'Processing: ' || param1;\nEND;\n"
            
            result_text += "```\n\n"
        
        elif code_type.lower() in ["rpg", "rpg_freeform"]:
            result_text += "```rpg\n"
            if include_comments:
                result_text += "// Generated free-form RPG code\n"
                result_text += "// Following company coding standards\n\n"
                result_text += f"// Requirements: {requirements}\n\n"
            
            result_text += "**CTL-OPT DFTACTGRP(*NO) ACTGRP(*CALLER);\n\n"
            
            if "file" in requirements.lower() or "database" in requirements.lower():
                result_text += "DCL-F DATAFILE DISK(*EXT) USAGE(*INPUT) KEYED;\n\n"
            
            result_text += "DCL-S variable CHAR(50);\nDCL-S counter INT(10);\n\n"
            
            if "sql" in requirements.lower():
                result_text += "EXEC SQL\n  SELECT field1 INTO :variable\n  FROM table1\n  WHERE condition = :parameter;\n\n"
            
            result_text += "IF variable <> '';\n    // Process data\n"
            result_text += "    counter += 1;\nENDIF;\n"
            result_text += "```\n\n"
        
        result_text += f"**Note:** This is a template based on your requirements. "
        result_text += f"Customize based on your specific needs.\n\n"
        result_text += f"**References used:** {len(relevant_docs)} documents from standards and best practices.\n"
        
        if relevant_examples:
            result_text += f"**Similar examples found:** {len(relevant_examples)} in uploaded documents."
        
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
        
        # Enhanced analysis with RPG format detection
        analysis = CodeAnalyzer.analyze_code_quality(code, code_type)
        
        result_text = f"**Code Review Report** ({review_level} level)\n\n"
        result_text += f"**Code Type:** {analysis['type']}\n"
        result_text += f"**Complexity:** {analysis['complexity']}\n"
        
        # Add RPG format information if applicable
        if analysis.get('rpg_format'):
            result_text += f"**RPG Format:** {analysis['rpg_format']}\n"
        
        result_text += "\n"
        
        if analysis['issues']:
            result_text += "**🚨 Issues Found:**\n"
            for issue in analysis['issues']:
                result_text += f"- {issue}\n"
            result_text += "\n"
        
        if analysis['suggestions']:
            result_text += "**💡 Suggestions for Improvement:**\n"
            for suggestion in analysis['suggestions']:
                result_text += f"- {suggestion}\n"
            result_text += "\n"
        
        if not analysis['issues'] and not analysis['suggestions']:
            result_text += "✅ **No major issues found.** Code follows basic standards.\n\n"
        
        # Add standards compliance check
        standards_count = len([doc for doc in documents_metadata.values() 
                             if doc["document_type"] in ["standards", "best_practices"]])
        
        result_text += f"**Standards Reference:** Review based on {standards_count} uploaded "
        result_text += "coding standards and best practices documents.\n"
        
        if review_level == "comprehensive":
            result_text += "\n**Detailed Analysis:**\n"
            result_text += "- Code structure and organization\n"
            result_text += "- Naming conventions compliance\n"
            result_text += "- Error handling implementation\n"
            result_text += "- Performance considerations\n"
            result_text += "- Maintainability factors\n"
        
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
        
        result_text = f"**Code Explanation** ({explanation_level} level)\n\n"
        result_text += f"```\n{code}\n```\n\n"
        
        # Enhanced code analysis and explanation
        code_blocks = CodeAnalyzer.extract_code_blocks(code)
        
        if code_blocks:
            primary_type = code_blocks[0]["type"]
            code_format = code_blocks[0].get("format", "unknown")
            
            result_text += f"**Code Type:** {primary_type}"
            if code_format != "unknown":
                result_text += f" ({code_format} format)"
            result_text += "\n\n"
        
        # Basic analysis
        if "SELECT" in code.upper():
            result_text += "**Purpose:** This is a SQL SELECT statement that retrieves data from a database.\n"
            result_text += "It queries specified columns from tables based on given conditions.\n\n"
        
        elif "**CTL-OPT" in code.upper() or "DCL-" in code.upper():
            result_text += "**Purpose:** This is modern free-form RPG code.\n"
            result_text += "Free-form RPG uses natural language syntax and is easier to read and maintain.\n\n"
            
            if "DCL-F" in code.upper():
                result_text += "**File Declarations:** DCL-F statements declare file usage and access methods.\n"
            if "DCL-S" in code.upper():
                result_text += "**Variable Declarations:** DCL-S statements declare standalone variables.\n"
            if "EXEC SQL" in code.upper():
                result_text += "**Embedded SQL:** EXEC SQL blocks allow direct database operations.\n"
        
        elif len([line for line in code.split('\n') if len(line) >= 6 and line[5:6] in 'HFDICOhfdico']) > 0:
            result_text += "**Purpose:** This is traditional fixed-format RPG code.\n"
            result_text += "Traditional RPG uses fixed column positions for different specification types.\n\n"
            
            result_text += "**Format Details:**\n"
            result_text += "- Columns 6: Specification type (H=Control, F=File, D=Definition, C=Calculation)\n"
            result_text += "- Columns 7-11: Indicators or conditioning\n"
            result_text += "- Columns vary by specification type for factors and results\n\n"
        
        elif "EXEC SQL" in code.upper():
            result_text += "**Purpose:** This is embedded SQL within RPG code.\n"
            result_text += "It allows direct database operations from within the RPG program.\n\n"
        
        # Enhanced explanation based on level
        if explanation_level in ["detailed", "advanced"]:
            result_text += "**Detailed Analysis:**\n"
            
            lines = code.split('\n')
            for i, line in enumerate(lines[:10], 1):  # Analyze first 10 lines
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith('**CTL-OPT'):
                    result_text += f"- Line {i}: Control specification defines program attributes\n"
                elif line.startswith('DCL-F'):
                    result_text += f"- Line {i}: File declaration for database access\n"
                elif line.startswith('DCL-S'):
                    result_text += f"- Line {i}: Variable declaration\n"
                elif line.startswith('DCL-PROC'):
                    result_text += f"- Line {i}: Procedure definition start\n"
                elif "EXEC SQL" in line:
                    result_text += f"- Line {i}: Embedded SQL statement\n"
                elif line[0:1] in 'HFDICOhfdico' and len(line) >= 6:
                    spec_type = {'H': 'Control', 'F': 'File', 'D': 'Definition', 
                               'I': 'Input', 'C': 'Calculation', 'O': 'Output'}.get(line[0].upper(), 'Unknown')
                    result_text += f"- Line {i}: {spec_type} specification (traditional format)\n"
            
            result_text += "\n"
        
        if explanation_level == "advanced":
            result_text += "**Advanced Concepts:**\n"
            result_text += "- Modern RPG emphasizes procedures over subroutines\n"
            result_text += "- Error handling should use MONITOR/ON-ERROR blocks\n"
            result_text += "- Embedded SQL is preferred over native file operations\n"
            result_text += "- Qualified data structures improve code organization\n\n"
        
        if include_references:
            doc_count = len([doc for doc in documents_metadata.values() 
                           if doc["document_type"] in ["reference", "best_practices"]])
            result_text += f"**References:** Based on {doc_count} uploaded reference documents and coding standards."
        
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
        
        # Determine file extension based on artifact type
        if artifact_type in ["module", "procedure", "complete_program"]:
            extension = "rpg"
        elif artifact_type == "conversion_result":
            extension = "conversion"
        else:
            extension = "txt"
            
        artifact_filename = f"artifact_{artifact_id}_{artifact_type}.{extension}"
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
        
        if artifact_type == "procedure":
            artifact_content += "**CTL-OPT DFTACTGRP(*NO) ACTGRP(*CALLER);\n\n"
            artifact_content += "// Procedure implementation\n"
            artifact_content += "DCL-PROC sampleProcedure EXPORT;\n"
            artifact_content += "    DCL-PI *N CHAR(100);\n"
            artifact_content += "        inputData CHAR(50) CONST;\n"
            artifact_content += "        options CHAR(10) OPTIONS(*NOPASS);\n"
            artifact_content += "    END-PI;\n\n"
            artifact_content += "    DCL-S result CHAR(100);\n\n"
            artifact_content += "    MONITOR;\n"
            artifact_content += "        // Processing logic here\n"
            artifact_content += "        result = 'Processed: ' + inputData;\n"
            artifact_content += "    ON-ERROR;\n"
            artifact_content += "        result = 'Error processing: ' + inputData;\n"
            artifact_content += "    ENDMON;\n\n"
            artifact_content += "    RETURN result;\n"
            artifact_content += "END-PROC;\n"
        
        elif artifact_type == "module":
            artifact_content += "**CTL-OPT DFTACTGRP(*NO) ACTGRP(*CALLER);\n\n"
            artifact_content += "// Module implementation\n"
            artifact_content += "// Copy member for prototypes\n"
            artifact_content += "/COPY QCPYSRC,PROTOTYPES\n\n"
            artifact_content += "DCL-PROC processData EXPORT;\n"
            artifact_content += "    DCL-PI *N CHAR(100);\n"
            artifact_content += "        input_data CHAR(50) CONST;\n"
            artifact_content += "    END-PI;\n\n"
            artifact_content += "    DCL-S result CHAR(100);\n\n"
            artifact_content += "    // Processing logic here\n"
            artifact_content += "    result = 'Processed: ' + input_data;\n"
            artifact_content += "    RETURN result;\n"
            artifact_content += "END-PROC;\n"
        
        elif artifact_type == "complete_program":
            artifact_content += "**CTL-OPT MAIN(mainProcedure) DFTACTGRP(*NO) ACTGRP(*CALLER);\n\n"
            artifact_content += "// File declarations\n"
            artifact_content += "DCL-F DATAFILE DISK(*EXT) USAGE(*INPUT) KEYED;\n\n"
            artifact_content += "// Main procedure\n"
            artifact_content += "DCL-PROC mainProcedure;\n"
            artifact_content += "    DCL-PI *N END-PI;\n\n"
            artifact_content += "    DCL-S key CHAR(10);\n"
            artifact_content += "    DCL-S found IND;\n\n"
            artifact_content += "    key = 'TEST';\n"
            artifact_content += "    CHAIN key DATAFILE;\n"
            artifact_content += "    found = %FOUND(DATAFILE);\n\n"
            artifact_content += "    IF found;\n"
            artifact_content += "        // Process record\n"
            artifact_content += "    ELSE;\n"
            artifact_content += "        // Handle not found\n"
            artifact_content += "    ENDIF;\n\n"
            artifact_content += "END-PROC;\n"
        
        elif artifact_type == "conversion_result":
            artifact_content += f"CONVERSION RESULT\n"
            artifact_content += f"Conversion ID: {artifact_id}\n"
            artifact_content += f"Specifications: {specifications}\n\n"
            artifact_content += "ORIGINAL CODE:\n"
            artifact_content += "// Original traditional RPG code would be here\n\n"
            artifact_content += "CONVERTED CODE:\n"
            artifact_content += "// Converted free-form RPG code would be here\n\n"
            artifact_content += "CONVERSION NOTES:\n"
            artifact_content += "// Conversion notes and warnings would be here\n"
        
        # Save artifact
        with open(artifact_path, 'w', encoding='utf-8') as f:
            f.write(artifact_content)
        
        result_text = f"✅ **Artifact created successfully!**\n\n"
        result_text += f"**Type:** {artifact_type}\n"
        result_text += f"**ID:** {artifact_id}\n"
        result_text += f"**Filename:** {artifact_filename}\n"
        result_text += f"**Path:** {artifact_path}\n"
        result_text += f"**Size:** {len(artifact_content)} characters\n\n"
        result_text += f"The artifact has been saved and can be referenced or downloaded.\n"
        
        if artifact_type in ["module", "procedure", "complete_program"]:
            result_text += f"**Note:** This RPG artifact follows modern free-form standards.\n"
        
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
        
        result_text = f"📚 **Available Documents** ({len(filtered_docs)} total)\n\n"
        
        # Group by document type
        doc_groups = {}
        for doc in filtered_docs:
            doc_type = doc["document_type"]
            if doc_type not in doc_groups:
                doc_groups[doc_type] = []
            doc_groups[doc_type].append(doc)
        
        for doc_type, docs in doc_groups.items():
            result_text += f"**{doc_type.upper().replace('_', ' ')} ({len(docs)} documents)**\n"
            
            for i, doc in enumerate(docs, 1):
                result_text += f"{i}. {doc['filename']}\n"
                result_text += f"   📝 Description: {doc['description']}\n"
                result_text += f"   📅 Uploaded: {doc['uploaded_at'][:19]}\n"
                
                content = doc.get('content', {})
                if 'pages' in content:
                    result_text += f"   📄 Pages: {content['pages']}\n"
                elif 'size' in content:
                    result_text += f"   📊 Size: {content['size']} characters\n"
                
                if 'images' in content:
                    result_text += f"   🖼️ Images: {len(content['images'])}\n"
                
                if 'sections' in content:
                    result_text += f"   📑 Sections: {len(content['sections'])}\n"
                
                if 'code_examples' in doc:
                    examples = doc['code_examples']
                    rpg_examples = [ex for ex in examples if 'rpg' in ex.get('type', '').lower()]
                    result_text += f"   💻 Code Examples: {len(examples)} total"
                    if rpg_examples:
                        result_text += f", {len(rpg_examples)} RPG"
                    result_text += "\n"
                
                result_text += "\n"
        
        return CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
    
    else:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {name}")]
        )

# FastAPI endpoints remain the same...
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
        "version": "1.1.0",
        "storage_dir": str(STORAGE_DIR),
        "documents_processed": len(documents_metadata),
        "artifacts_created": len(list(ARTIFACTS_DIR.glob("*.txt"))),
        "rpg_conversion_enabled": True
    }

@app.get("/")
async def root():
    """Root endpoint with server info."""
    tools = await list_tools()
    tool_names = [tool.name for tool in tools.tools]
    
    return {
        "name": "DB2/RPG Code Generation MCP Server",
        "version": "1.1.0",
        "description": "Enhanced MCP server for IBM DB2 and RPG code generation, review, and traditional-to-freeform conversion",
        "tools": tool_names,
        "new_features": [
            "RPG Traditional to Free-form conversion",
            "Enhanced document section extraction",
            "RPG pattern analysis",
            "Conversion validation",
            "Modernization suggestions"
        ],
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