#!/usr/bin/env python3
"""Index KinnyCode Memory project to remote server."""
import os
import json
import httpx
from pathlib import Path

# Configuration
SERVER_URL = "http://192.168.2.111:8007"
PROJECT_ID = "a67d4e5165ff6b92"
PROJECT_PATH = Path("F:\\kinnyCodeMemory")

# File extensions to index
INCLUDE_EXTENSIONS = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".sh", ".ps1", ".bat", ".cmd"}

# Directories to exclude
EXCLUDE_DIRS = {"node_modules", "__pycache__", ".git", ".venv", "venv", "env", ".pytest_cache", "lancedb_memory_db", ".opencode", ".kinnycode", "dist", "build", ".eggs", "*.egg-info"}

def should_include(file_path: Path) -> bool:
    """Check if file should be included."""
    # Check extension
    if file_path.suffix.lower() not in INCLUDE_EXTENSIONS:
        return False
    
    # Check excluded directories
    for part in file_path.parts:
        if part in EXCLUDE_DIRS:
            return False
    
    return True

def get_language(file_path: Path) -> str:
    """Get language from file extension."""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".md": "markdown",
        ".txt": "text",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".cfg": "config",
        ".ini": "config",
        ".sh": "shell",
        ".ps1": "powershell",
        ".bat": "batch",
        ".cmd": "batch",
    }
    return ext_map.get(file_path.suffix.lower(), "text")

def index_file(client: httpx.Client, file_path: Path) -> bool:
    """Index a single file."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        relative_path = file_path.relative_to(PROJECT_PATH)
        
        response = client.post(
            f"{SERVER_URL}/index-file",
            json={
                "file_path": str(relative_path),
                "content": content,
                "language": get_language(file_path),
                "project_id": PROJECT_ID,
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            chunks = result.get("chunks_created", 0)
            print(f"  ✅ {relative_path} ({chunks} chunks)")
            return True
        else:
            print(f"  ❌ {relative_path}: {response.status_code} - {response.text[:100]}")
            return False
            
    except Exception as e:
        print(f"  ❌ {file_path.name}: {e}")
        return False

def main():
    print("=" * 60)
    print("KinnyCode Memory - Project Indexer")
    print("=" * 60)
    print(f"\nServer: {SERVER_URL}")
    print(f"Project ID: {PROJECT_ID}")
    print(f"Project Path: {PROJECT_PATH}")
    
    # Collect files
    print("\n📁 Collecting files...")
    files = []
    for file_path in PROJECT_PATH.rglob("*"):
        if file_path.is_file() and should_include(file_path):
            files.append(file_path)
    
    print(f"   Found {len(files)} files to index")
    
    # Sort by size (smallest first for faster feedback)
    files.sort(key=lambda f: f.stat().st_size)
    
    # Index files
    print("\n📤 Indexing files...")
    success_count = 0
    error_count = 0
    
    with httpx.Client(timeout=60.0) as client:
        # Test connection first
        try:
            response = client.get(f"{SERVER_URL}/health")
            if response.status_code == 200:
                print("   ✅ Server connection OK")
            else:
                print(f"   ❌ Server error: {response.status_code}")
                return
        except Exception as e:
            print(f"   ❌ Connection error: {e}")
            return
        
        for i, file_path in enumerate(files, 1):
            print(f"\n[{i}/{len(files)}] {file_path.name}...")
            if index_file(client, file_path):
                success_count += 1
            else:
                error_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Summary")
    print("=" * 60)
    print(f"   ✅ Success: {success_count}")
    print(f"   ❌ Errors: {error_count}")
    print(f"   📁 Total: {len(files)}")
    
    # Get project info
    print("\n📈 Project Info:")
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{SERVER_URL}/project-info",
                json={"project_id": PROJECT_ID}
            )
            if response.status_code == 200:
                info = response.json()
                stats = info.get("stats", {})
                print(f"   Code chunks: {stats.get('code_chunks', 0)}")
                print(f"   Document chunks: {stats.get('document_chunks', 0)}")
                print(f"   Conversations: {stats.get('conversations', 0)}")
                print(f"   Decisions: {stats.get('decisions', 0)}")
                print(f"   Tasks: {stats.get('tasks', 0)}")
    except Exception as e:
        print(f"   Error getting project info: {e}")

if __name__ == "__main__":
    main()
