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

class CodeGenerationClient:
    """Azure OpenAI client with MCP tools for code generation."""
    
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
    
    async def chat_completion(self, messages: List[Dict[str, str]], max_tool_calls: int = 10) -> str:
        """Chat completion with MCP tool support."""
        
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

    async def generate_code(self, requirements: str, code_type: str = "sql") -> str:
        """Generate code based on requirements."""
        system_prompt = f"""You are a specialist in IBM DB2 and RPG code generation. 
        
        Your task is to generate high-quality, production-ready {code_type.upper()} code based on the user's requirements.
        
        IMPORTANT GUIDELINES:
        1. Always search for relevant reference documents first using search_references
        2. Extract relevant code examples using extract_code_examples 
        3. Follow the coding standards and best practices from uploaded documents
        4. Generate clean, well-commented, and maintainable code
        5. Include error handling where appropriate
        6. If the code is large, use create_artifact to manage content
        
        Always prioritize information from uploaded reference documents over general knowledge."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Generate {code_type} code for: {requirements}"}
        ]
        
        return await self.chat_completion(messages)
    
    async def review_code(self, code: str, code_type: str = "sql") -> str:
        """Review code against standards."""
        system_prompt = f"""You are a code reviewer specializing in IBM DB2 and RPG code.
        
        Your task is to review the provided code against company standards and best practices.
        
        REVIEW PROCESS:
        1. Use search_references to find relevant coding standards
        2. Use review_code tool to analyze the code
        3. Provide detailed feedback on:
           - Code quality and adherence to standards
           - Performance considerations
           - Security issues
           - Maintainability
           - Best practice compliance
        
        Always reference specific standards from uploaded documents."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Please review this {code_type} code:\n\n```{code_type}\n{code}\n```"}
        ]
        
        return await self.chat_completion(messages)
    
    async def explain_code(self, code: str, level: str = "intermediate") -> str:
        """Explain code functionality."""
        system_prompt = f"""You are a technical instructor specializing in IBM DB2 and RPG.
        
        Your task is to explain the provided code in a clear and educational manner.
        
        EXPLANATION PROCESS:
        1. Use explain_code tool to analyze the code
        2. Search for relevant documentation using search_references
        3. Provide explanations at the {level} level
        4. Include references to official documentation when available
        
        Make explanations clear, accurate, and educational."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Please explain this code at {level} level:\n\n```\n{code}\n```"}
        ]
        
        return await self.chat_completion(messages)
    
    async def create_large_artifact(self, artifact_type: str, specifications: str) -> str:
        """Create large code artifacts."""
        system_prompt = """You are a senior developer creating comprehensive code artifacts.
        
        Your task is to create large, well-structured code artifacts like complete modules or programs.
        
        ARTIFACT CREATION PROCESS:
        1. Search for relevant standards and examples
        2. Use create_artifact tool for large code generation
        3. Ensure proper structure and documentation
        4. Follow company coding standards
        
        Create production-ready, comprehensive code artifacts."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Create a {artifact_type} with these specifications: {specifications}"}
        ]
        
        return await self.chat_completion(messages)

async def interactive_code_session():
    """Interactive code generation and review session."""
    
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
        code_client = CodeGenerationClient(mcp_client)
        
        print("🚀 DB2/RPG Code Generation Assistant")
        print("=" * 50)
        print("Commands:")
        print("  'upload <file_path>' - Upload reference document")
        print("  'generate <type> <requirements>' - Generate code")
        print("  'review <type> <code>' - Review code")
        print("  'explain <code>' - Explain code")
        print("  'artifact <type> <specs>' - Create large artifact")
        print("  'docs' - List uploaded documents")
        print("  'artifacts' - List generated artifacts")
        print("  'help' - Show this help")
        print("  'quit' - Exit")
        print()
        
        # Check server connection
        try:
            tools = await code_client.get_available_tools()
            print(f"✅ Connected to MCP server. Available tools: {len(tools)}")
        except Exception as e:
            print(f"❌ Cannot connect to MCP server: {e}")
            print("Make sure the server is running: python mcp-server.py")
            return
        
        print()
        
        while True:
            try:
                user_input = input("Code Assistant> ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    break
                
                elif user_input.lower() == 'help':
                    print("Available commands:")
                    print("  upload - Upload reference documents (PDF/Markdown)")
                    print("  generate - Generate new code based on requirements")
                    print("  review - Review existing code against standards")
                    print("  explain - Get explanations of code functionality")
                    print("  artifact - Create large code artifacts")
                    print("  docs - List all uploaded reference documents")
                    print("  artifacts - List all generated artifacts")
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
                        doc_type = input("Document type (standards/procedures/best_practices/reference/examples): ") or "reference"
                        description = input("Description (optional): ") or f"Uploaded {filename}"
                        
                        process_result = await mcp_client.call_tool("upload_document", {
                            "filename": filename,
                            "document_type": doc_type,
                            "description": description
                        })
                        print(f"📋 {process_result}")
                    
                    continue
                
                elif user_input.startswith('generate '):
                    parts = user_input[9:].split(' ', 1)
                    if len(parts) < 2:
                        print("Usage: generate <type> <requirements>")
                        print("Types: sql, db2, rpg, procedure")
                        continue
                    
                    code_type, requirements = parts
                    print(f"🔧 Generating {code_type} code...")
                    
                    response = await code_client.generate_code(requirements, code_type)
                    print(f"Generated Code:\n{response}\n")
                    continue
                
                elif user_input.startswith('review '):
                    parts = user_input[7:].split(' ', 1)
                    if len(parts) < 2:
                        print("Usage: review <type> <code>")
                        continue
                    
                    code_type = parts[0]
                    print("Enter your code (end with '###' on a new line):")
                    code_lines = []
                    while True:
                        line = input()
                        if line.strip() == '###':
                            break
                        code_lines.append(line)
                    
                    code = '\n'.join(code_lines)
                    print(f"🔍 Reviewing {code_type} code...")
                    
                    response = await code_client.review_code(code, code_type)
                    print(f"Review Results:\n{response}\n")
                    continue
                
                elif user_input.startswith('explain '):
                    print("Enter your code (end with '###' on a new line):")
                    code_lines = []
                    while True:
                        line = input()
                        if line.strip() == '###':
                            break
                        code_lines.append(line)
                    
                    code = '\n'.join(code_lines)
                    level = input("Explanation level (beginner/intermediate/advanced): ") or "intermediate"
                    
                    print(f"📖 Explaining code at {level} level...")
                    
                    response = await code_client.explain_code(code, level)
                    print(f"Code Explanation:\n{response}\n")
                    continue
                
                elif user_input.startswith('artifact '):
                    parts = user_input[9:].split(' ', 1)
                    if len(parts) < 2:
                        print("Usage: artifact <type> <specifications>")
                        print("Types: module, procedure, package, complete_program")
                        continue
                    
                    artifact_type, specifications = parts
                    print(f"🏗️ Creating {artifact_type} artifact...")
                    
                    response = await code_client.create_large_artifact(artifact_type, specifications)
                    print(f"Artifact Created:\n{response}\n")
                    continue
                
                elif user_input:
                    # General conversation
                    system_msg = """You are a DB2/RPG coding assistant. Help with code-related questions, 
                    reference uploaded documents when possible, and provide accurate technical guidance."""
                    
                    response = await code_client.chat_completion([
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_input}
                    ])
                    print(f"Assistant: {response}\n")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}\n")
        
        print("👋 Goodbye!")

async def main():
    """Main function for command line usage."""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        await interactive_code_session()
    else:
        # Run example usage
        print("🚀 DB2/RPG Code Generation Client")
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
            code_client = CodeGenerationClient(mcp_client)
            
            # Test connection
            try:
                tools = await code_client.get_available_tools()
                print(f"✅ Connected to MCP server. Available tools: {len(tools)}")
                
                # List available tools
                print("\n📚 Available Tools:")
                for tool in tools:
                    print(f"  - {tool['function']['name']}: {tool['function']['description']}")
                
                # Example usage
                print("\n🔧 Example: Generate SQL code")
                requirements = "Create a SELECT statement to get customer information with order history"
                response = await code_client.generate_code(requirements, "sql")
                print(f"Generated Code:\n{response}")
                
                print("\n💡 For interactive mode, run: python client.py interactive")
                
            except Exception as e:
                print(f"❌ Cannot connect to MCP server: {e}")
                print("Make sure the server is running: python mcp-server.py")

if __name__ == "__main__":
    asyncio.run(main())
