#!/usr/bin/env python3

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

import aiohttp
from openai import AsyncAzureOpenAI

class MCPClient:
    """HTTP client for MCP server communication."""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.environ.get("MCP_SERVER_URL", "http://localhost:8000")
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from MCP server."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
        
        async with self.session.post(
            f"{self.base_url}/mcp",
            json=request_data
        ) as response:
            result = await response.json()
            if "result" in result:
                return result["result"]["tools"]
            return []
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on the MCP server."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments
            }
        }
        
        async with self.session.post(
            f"{self.base_url}/mcp",
            json=request_data
        ) as response:
            result = await response.json()
            if "result" in result and "content" in result["result"]:
                content = result["result"]["content"]
                if content and len(content) > 0:
                    return content[0]["text"]
            return "No result"
    
    async def upload_document(self, file_path: str) -> Dict[str, Any]:
        """Upload a document to the server."""
        try:
            with open(file_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename=os.path.basename(file_path))
                
                async with self.session.post(
                    f"{self.base_url}/upload",
                    data=data
                ) as response:
                    return await response.json()
        except Exception as e:
            return {"error": str(e)}
    
    async def list_documents(self) -> Dict[str, Any]:
        """List all documents on the server."""
        async with self.session.get(f"{self.base_url}/documents") as response:
            return await response.json()
    
    async def list_artifacts(self) -> Dict[str, Any]:
        """List all generated artifacts."""
        async with self.session.get(f"{self.base_url}/artifacts") as response:
            return await response.json()

class RPGConversionClient:
    """Specialized client for RPG conversion workflows."""
    
    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client
        
        # Initialize Azure OpenAI client
        self.client = AsyncAzureOpenAI(
            api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT")
        )
        
        self.deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
        self.max_tokens = 128000  # Context window limit
    
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get available tools from MCP server and format for OpenAI."""
        mcp_tools = await self.mcp_client.list_tools()
        
        # Convert MCP tools to OpenAI function format
        openai_tools = []
        for tool in mcp_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"]
                }
            })
        
        return openai_tools
    
    def _count_tokens(self, text: str) -> int:
        """Rough token counting (1 token ≈ 4 characters for estimation)."""
        return len(text) // 4
    
    def _truncate_content(self, content: str, max_tokens: int = 100000) -> str:
        """Truncate content to fit within token limits."""
        estimated_tokens = self._count_tokens(content)
        if estimated_tokens <= max_tokens:
            return content
        
        # Calculate truncation point (leave some buffer)
        target_chars = max_tokens * 4 * 0.8  # 80% to be safe
        truncated = content[:int(target_chars)]
        return truncated + "\n\n[Content truncated due to length limitations...]"
    
    async def analyze_traditional_rpg(self, code: str) -> str:
        """Analyze traditional RPG code structure."""
        return await self.mcp_client.call_tool("analyze_rpg_syntax", {
            "code": code,
            "include_conversion_plan": True
        })
    
    async def convert_rpg_code(self, code: str, apply_standards: bool = True) -> str:
        """Convert traditional RPG to free-form with standards application."""
        return await self.mcp_client.call_tool("convert_rpg_to_freeform", {
            "code": code,
            "apply_standards": apply_standards,
            "include_comments": True,
            "validation_level": "detailed"
        })
    
    async def validate_conversion(self, original_code: str, converted_code: str) -> str:
        """Validate converted code against standards."""
        return await self.mcp_client.call_tool("validate_conversion", {
            "original_code": original_code,
            "converted_code": converted_code
        })
    
    async def get_conversion_standards(self) -> str:
        """Extract RPG conversion patterns from uploaded standards."""
        return await self.mcp_client.call_tool("extract_rpg_patterns", {
            "pattern_type": "conversion_rules",
            "format": "both"
        })
    
    async def suggest_modernization(self, code: str, focus_areas: List[str] = None) -> str:
        """Get modernization suggestions for RPG code."""
        if focus_areas is None:
            focus_areas = ["error_handling", "procedures", "maintainability"]
        
        return await self.mcp_client.call_tool("suggest_modernization", {
            "code": code,
            "focus_areas": focus_areas
        })
    
    async def compare_code_styles(self, operation_type: str) -> str:
        """Compare traditional vs free-form coding styles."""
        return await self.mcp_client.call_tool("compare_code_styles", {
            "operation_type": operation_type,
            "show_examples": True
        })
    
    async def chat_completion(self, messages: List[Dict[str, str]], max_tool_calls: int = 10) -> str:
        """Chat completion with MCP tool support for RPG conversion."""
        
        # Get available tools
        tools = await self.get_available_tools()
        
        current_messages = messages.copy()
        tool_call_count = 0
        
        # Truncate messages if they're too long
        for message in current_messages:
            if "content" in message:
                message["content"] = self._truncate_content(message["content"])
        
        while tool_call_count < max_tool_calls:
            # Make OpenAI request with tools
            response = await self.client.chat.completions.create(
                model=self.deployment_name,
                messages=current_messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=4000  # Limit response tokens
            )
            
            message = response.choices[0].message
            
            # If no tool calls, return the response
            if not message.tool_calls:
                return message.content
            
            # Add assistant message with tool calls
            current_messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                    }
                    for tool_call in message.tool_calls
                ]
            })
            
            # Execute tool calls
            for tool_call in message.tool_calls:
                try:
                    # Parse arguments
                    arguments = json.loads(tool_call.function.arguments)
                    
                    # Call MCP tool
                    result = await self.mcp_client.call_tool(
                        tool_call.function.name,
                        arguments
                    )
                    
                    # Truncate tool result if too long
                    result = self._truncate_content(result, max_tokens=10000)
                    
                    # Add tool result to messages
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })
                    
                except Exception as e:
                    # Add error result
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: {str(e)}"
                    })
            
            tool_call_count += 1
            
            # Check total token count and truncate if necessary
            total_content = " ".join([msg.get("content", "") for msg in current_messages])
            if self._count_tokens(total_content) > self.max_tokens * 0.8:
                # Remove older messages to stay within limits
                current_messages = current_messages[-5:]  # Keep last 5 messages
        
        return "Maximum tool calls reached"

async def interactive_rpg_conversion_session():
    """Interactive RPG conversion and analysis session."""
    
    # Check required environment variables
    required_vars = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT_NAME"
    ]
    
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if missing_vars:
        print(f"❌ Missing required environment variables: {missing_vars}")
        print("Please run the env_var_init_client.sh script first.")
        return
    
    async with MCPClient() as mcp_client:
        rpg_client = RPGConversionClient(mcp_client)
        
        print("🔄 RPG Traditional-to-Freeform Conversion Assistant")
        print("=" * 60)
        print("Enhanced Commands:")
        print("  'upload <file_path>' - Upload reference document")
        print("  'analyze <code>' - Analyze traditional RPG code")
        print("  'convert <code>' - Convert traditional RPG to free-form")
        print("  'validate' - Validate a conversion (enter both codes)")
        print("  'standards' - View conversion standards from documents")
        print("  'modernize <code>' - Get modernization suggestions")
        print("  'compare <operation>' - Compare coding styles")
        print("  'patterns <type>' - Extract specific RPG patterns")
        print("  'sections <title>' - Get document sections")
        print("  'docs' - List uploaded documents")
        print("  'artifacts' - List generated artifacts")
        print("  'help' - Show this help")
        print("  'quit' - Exit")
        print()
        
        # Check server connection
        try:
            tools = await rpg_client.get_available_tools()
            print(f"✅ Connected to enhanced MCP server. Available tools: {len(tools)}")
            
            # Show RPG-specific tools
            rpg_tools = [tool for tool in tools if 'rpg' in tool['function']['name'].lower() or 'convert' in tool['function']['name'].lower()]
            print(f"🔧 RPG conversion tools available: {len(rpg_tools)}")
            for tool in rpg_tools:
                print(f"   - {tool['function']['name']}")
        except Exception as e:
            print(f"❌ Cannot connect to MCP server: {e}")
            print("Make sure the enhanced server is running: python mcp-server.py")
            return
        
        print()
        
        while True:
            try:
                user_input = input("RPG Assistant> ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    break
                
                elif user_input.lower() == 'help':
                    print("RPG Conversion Commands:")
                    print("  upload - Upload RPG standards and conversion guides")
                    print("  analyze - Analyze traditional RPG code structure")
                    print("  convert - Convert traditional RPG to free-form")
                    print("  validate - Validate conversion results")
                    print("  standards - View conversion rules from documents")
                    print("  modernize - Get modernization suggestions")
                    print("  compare - Compare traditional vs free-form styles")
                    print("  patterns - Extract RPG patterns from documents")
                    print("  sections - Get specific document sections")
                    continue
                
                elif user_input.lower() == 'docs':
                    docs = await mcp_client.list_documents()
                    print(f"📚 Documents: {docs.get('total_files', 0)}")
                    for doc in docs.get('files', []):
                        status = "✅ Processed" if doc['processed'] else "⏳ Uploaded"
                        print(f"  - {doc['filename']} ({doc['size']} bytes) {status}")
                    continue
                
                elif user_input.lower() == 'artifacts':
                    artifacts = await mcp_client.list_artifacts()
                    print(f"📁 Artifacts: {artifacts.get('total_artifacts', 0)}")
                    for artifact in artifacts.get('artifacts', []):
                        print(f"  - {artifact['filename']} ({artifact['size']} bytes)")
                    continue
                
                elif user_input.lower() == 'standards':
                    print("📋 Extracting conversion standards from documents...")
                    result = await rpg_client.get_conversion_standards()
                    print(f"Conversion Standards:\n{result}\n")
                    continue
                
                elif user_input.startswith('upload '):
                    file_path = user_input[7:].strip()
                    if not os.path.exists(file_path):
                        print(f"❌ File not found: {file_path}")
                        continue
                    
                    print(f"📤 Uploading {file_path}...")
                    result = await mcp_client.upload_document(file_path)
                    
                    if 'error' in result:
                        print(f"❌ Upload failed: {result['error']}")
                    else:
                        print(f"✅ {result['message']}")
                        
                        # Process the document
                        filename = os.path.basename(file_path)
                        doc_type = input("Document type (standards/conversion_guide/best_practices/reference/examples): ") or "reference"
                        description = input("Description (optional): ") or f"Uploaded {filename}"
                        
                        process_result = await mcp_client.call_tool("upload_document", {
                            "filename": filename,
                            "document_type": doc_type,
                            "description": description
                        })
                        print(f"📋 {process_result}")
                    
                    continue
                
                elif user_input.startswith('analyze '):
                    print("Enter your traditional RPG code (end with '###' on a new line):")
                    code_lines = []
                    while True:
                        line = input()
                        if line.strip() == '###':
                            break
                        code_lines.append(line)
                    
                    code = '\n'.join(code_lines)
                    print("🔍 Analyzing traditional RPG code...")
                    
                    result = await rpg_client.analyze_traditional_rpg(code)
                    print(f"Analysis Results:\n{result}\n")
                    continue
                
                elif user_input.startswith('convert '):
                    print("Enter your traditional RPG code (end with '###' on a new line):")
                    code_lines = []
                    while True:
                        line = input()
                        if line.strip() == '###':
                            break
                        code_lines.append(line)
                    
                    code = '\n'.join(code_lines)
                    apply_standards = input("Apply uploaded coding standards? (y/n): ").lower() != 'n'
                    
                    print("🔄 Converting to free-form RPG...")
                    
                    result = await rpg_client.convert_rpg_code(code, apply_standards)
                    print(f"Conversion Results:\n{result}\n")
                    continue
                
                elif user_input.lower() == 'validate':
                    print("Enter original traditional RPG code (end with '###' on a new line):")
                    original_lines = []
                    while True:
                        line = input()
                        if line.strip() == '###':
                            break
                        original_lines.append(line)
                    
                    print("Enter converted free-form RPG code (end with '###' on a new line):")
                    converted_lines = []
                    while True:
                        line = input()
                        if line.strip() == '###':
                            break
                        converted_lines.append(line)
                    
                    original_code = '\n'.join(original_lines)
                    converted_code = '\n'.join(converted_lines)
                    
                    print("🔍 Validating conversion...")
                    
                    result = await rpg_client.validate_conversion(original_code, converted_code)
                    print(f"Validation Results:\n{result}\n")
                    continue
                
                elif user_input.startswith('modernize '):
                    print("Enter your RPG code (end with '###' on a new line):")
                    code_lines = []
                    while True:
                        line = input()
                        if line.strip() == '###':
                            break
                        code_lines.append(line)
                    
                    code = '\n'.join(code_lines)
                    focus_areas = input("Focus areas (comma-separated): error_handling,procedures,maintainability,sql_integration: ").split(',')
                    focus_areas = [area.strip() for area in focus_areas if area.strip()]
                    
                    if not focus_areas:
                        focus_areas = ["error_handling", "procedures", "maintainability"]
                    
                    print("💡 Generating modernization suggestions...")
                    
                    result = await rpg_client.suggest_modernization(code, focus_areas)
                    print(f"Modernization Suggestions:\n{result}\n")
                    continue
                
                elif user_input.startswith('compare '):
                    operation_type = user_input[8:].strip()
                    if not operation_type:
                        print("Available operations: file_operations, calculations, conditions, loops, procedures, error_handling")
                        operation_type = input("Enter operation type: ").strip()
                    
                    print(f"📊 Comparing {operation_type} styles...")
                    
                    result = await rpg_client.compare_code_styles(operation_type)
                    print(f"Style Comparison:\n{result}\n")
                    continue
                
                elif user_input.startswith('patterns '):
                    pattern_type = user_input[9:].strip()
                    if not pattern_type:
                        print("Available patterns: naming_conventions, error_handling, file_operations, data_structures, procedures, conversion_rules")
                        pattern_type = input("Enter pattern type: ").strip()
                    
                    print(f"🔍 Extracting {pattern_type} patterns...")
                    
                    result = await mcp_client.call_tool("extract_rpg_patterns", {
                        "pattern_type": pattern_type,
                        "format": "both"
                    })
                    print(f"RPG Patterns:\n{result}\n")
                    continue
                
                elif user_input.startswith('sections '):
                    section_title = user_input[9:].strip()
                    if not section_title:
                        section_title = input("Enter section title to search for: ").strip()
                    
                    print(f"📖 Searching for section '{section_title}'...")
                    
                    result = await mcp_client.call_tool("get_document_sections", {
                        "section_title": section_title
                    })
                    print(f"Document Sections:\n{result}\n")
                    continue
                
                elif user_input:
                    # General RPG conversation with AI
                    system_msg = """You are an expert RPG developer specializing in traditional to free-form conversions. 
                    
                    Your expertise includes:
                    - Analyzing traditional fixed-format RPG code
                    - Converting to modern free-form RPG
                    - Applying coding standards from uploaded documents
                    - Suggesting modernization techniques
                    - Validating conversions
                    
                    Always reference uploaded coding standards and use the available tools to provide accurate, 
                    standards-compliant advice for RPG development and conversion projects."""
                    
                    response = await rpg_client.chat_completion([
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_input}
                    ])
                    print(f"RPG Expert: {response}\n")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}\n")
        
        print("👋 Thanks for using the RPG Conversion Assistant!")

async def main():
    """Main function for command line usage."""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        await interactive_rpg_conversion_session()
    else:
        # Run example usage
        print("🔄 Enhanced RPG Conversion Client")
        print("=" * 40)
        
        # Check environment
        required_vars = [
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT_NAME"
        ]
        
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        if missing_vars:
            print(f"❌ Missing required environment variables: {missing_vars}")
            print("Please run the env_var_init_client.sh script first.")
            return
        
        async with MCPClient() as mcp_client:
            rpg_client = RPGConversionClient(mcp_client)
            
            # Test connection
            try:
                tools = await rpg_client.get_available_tools()
                print(f"✅ Connected to enhanced MCP server. Available tools: {len(tools)}")
                
                # List RPG-specific tools
                print("\n🔧 RPG Conversion Tools:")
                rpg_tools = [tool for tool in tools if any(keyword in tool['function']['name'].lower() 
                           for keyword in ['rpg', 'convert', 'analyze', 'modernize', 'validate'])]
                
                for tool in rpg_tools:
                    print(f"  - {tool['function']['name']}: {tool['function']['description']}")
                
                # Example: Analyze some traditional RPG code
                print("\n📝 Example: Analyzing traditional RPG code")
                sample_rpg = """H DFTACTGRP(*NO) ACTGRP(*CALLER)
F CUSTFILE  IF   E           K DISK
D customerID      S              7P 0
D customerName    S             50A
C                   CHAIN     12345         CUSTFILE
C                   IF        %FOUND(CUSTFILE)
C                   EVAL      customerName = CFNAME
C                   ENDIF"""
                
                analysis_result = await rpg_client.analyze_traditional_rpg(sample_rpg)
                print(f"Analysis Result:\n{analysis_result}")
                
                print("\n💡 For interactive RPG conversion mode, run: python client.py interactive")
                
            except Exception as e:
                print(f"❌ Cannot connect to MCP server: {e}")
                print("Make sure the enhanced server is running: python mcp-server.py")

if __name__ == "__main__":
    asyncio.run(main())