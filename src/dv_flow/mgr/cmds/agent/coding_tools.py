#****************************************************************************
#* coding_tools.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#*
#****************************************************************************
"""Fallback coding @function_tool wrappers (shell, file, grep).

These are used when MCP servers (mcp-shell-server, server-filesystem, etc.)
are not available. They are functional but lack MCP-level sandboxing.
"""

import asyncio
import os
import shutil
import subprocess
from typing import Optional

from agents import function_tool


@function_tool
async def shell_exec(command: str, timeout: int = 30, cwd: str = "") -> str:
    """Execute a shell command and return its output.

    Args:
        command: The shell command to run (passed to bash -c).
        timeout: Maximum seconds to wait (default 30).
        cwd: Working directory for the command (default: current directory).

    Returns:
        JSON-like string with stdout, stderr, and exit code.
    """
    import json
    work_dir = cwd if cwd else os.getcwd()
    try:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
        )
        return json.dumps({
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"exit_code": -1, "stdout": "", "stderr": f"Command timed out after {timeout}s"})
    except Exception as e:
        return json.dumps({"exit_code": -1, "stdout": "", "stderr": str(e)})


@function_tool
async def read_file(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """Read the contents of a file.

    Args:
        path: Absolute or relative path to the file.
        start_line: First line to return (1-indexed; 0 means start of file).
        end_line: Last line to return inclusive (0 means end of file).

    Returns:
        File contents as a string, or an error message prefixed with 'ERROR:'.
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            if start_line == 0 and end_line == 0:
                return f.read()
            lines = f.readlines()
        s = max(0, start_line - 1)
        e = end_line if end_line > 0 else len(lines)
        return "".join(lines[s:e])
    except Exception as ex:
        return f"ERROR: {ex}"


@function_tool
async def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed.

    Args:
        path: Absolute or relative path to write.
        content: Text content to write.

    Returns:
        'OK' on success, or an error message prefixed with 'ERROR:'.
    """
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return "OK"
    except Exception as ex:
        return f"ERROR: {ex}"


@function_tool
async def apply_patch(path: str, patch: str) -> str:
    """Apply a unified diff patch to a file.

    The patch must be in unified diff format (as produced by `diff -u` or `git diff`).

    Args:
        path: Path to the file to patch.
        patch: Unified diff content.

    Returns:
        'OK' on success, or an error message prefixed with 'ERROR:'.
    """
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as pf:
            pf.write(patch)
            patch_path = pf.name
        result = subprocess.run(
            ["patch", "-u", path, patch_path],
            capture_output=True, text=True,
        )
        os.unlink(patch_path)
        if result.returncode != 0:
            return f"ERROR: patch failed:\n{result.stderr}"
        return "OK"
    except Exception as ex:
        return f"ERROR: {ex}"


@function_tool
async def list_directory(path: str = ".", recursive: bool = False, pattern: str = "") -> str:
    """List directory contents.

    Args:
        path: Directory path (default: current directory).
        recursive: Whether to list recursively (default False).
        pattern: Optional glob pattern to filter files (e.g., '*.py').

    Returns:
        Newline-separated list of file paths, or an error message prefixed with 'ERROR:'.
    """
    import fnmatch
    try:
        results = []
        if recursive:
            for root, dirs, files in os.walk(path):
                # Skip hidden dirs
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), path)
                    if not pattern or fnmatch.fnmatch(f, pattern):
                        results.append(rel)
        else:
            for entry in sorted(os.listdir(path)):
                if not pattern or fnmatch.fnmatch(entry, pattern):
                    full = os.path.join(path, entry)
                    suffix = "/" if os.path.isdir(full) else ""
                    results.append(entry + suffix)
        return "\n".join(results)
    except Exception as ex:
        return f"ERROR: {ex}"


@function_tool
async def grep_search(pattern: str, path: str = ".", glob: str = "", recursive: bool = True) -> str:
    """Search files for a regex pattern.

    Uses ripgrep (rg) if available, otherwise falls back to grep.

    Args:
        pattern: Regular expression to search for.
        path: Directory or file path to search (default: current directory).
        glob: Optional glob to restrict which files are searched (e.g., '*.py').
        recursive: Search recursively (default True).

    Returns:
        Matching lines in 'file:line:content' format, or an error message prefixed with 'ERROR:'.
    """
    try:
        if shutil.which("rg"):
            cmd = ["rg", "--no-heading", "--line-number", pattern, path]
            if glob:
                cmd += ["--glob", glob]
            if not recursive:
                cmd += ["--max-depth", "1"]
        else:
            cmd = ["grep", "-rn" if recursive else "-n", pattern, path]
            if glob:
                cmd += ["--include", glob]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.stdout or "(no matches)"
    except subprocess.TimeoutExpired:
        return "ERROR: search timed out"
    except Exception as ex:
        return f"ERROR: {ex}"


def build_coding_tools():
    """Return the list of coding fallback tools."""
    return [shell_exec, read_file, write_file, apply_patch, list_directory, grep_search]
