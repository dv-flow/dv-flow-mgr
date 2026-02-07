#****************************************************************************
#* agent_tool_http.py
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
import os
import logging
import hashlib
import asyncio
import aiohttp
from urllib.parse import urlparse, urljoin
from pydantic import BaseModel
from typing import Optional
from dv_flow.mgr import TaskDataResult, TaskMarker, SeverityE

_log = logging.getLogger("AgentToolHttp")


class AgentToolHttpMemento(BaseModel):
    """Memento for tracking AgentToolHttp execution state"""
    url_hash: str
    validation_timestamp: Optional[float] = None


class AgentToolData(BaseModel):
    """Data item for AgentTool output"""
    type: str = "std.AgentTool"
    command: str = ""
    args: list = []
    url: str = ""
    
    model_config = {"extra": "allow"}


async def AgentToolHttp(runner, input) -> TaskDataResult:
    """
    Configure an MCP server using HTTP/SSE transport.
    
    Parameters:
    - url: Base URL of the MCP server
    - validate: Whether to validate URL is accessible (default: false)
    - health_check_path: Optional path for health check
    - headers: Optional HTTP headers (e.g., Authorization)
    - timeout: Timeout for validation requests (default: 5 seconds)
    
    Returns TaskDataResult with AgentTool output data.
    """
    _log.debug(f"AgentToolHttp task: {input.name}")
    
    status = 0
    markers = []
    changed = False
    output = []
    
    # Load existing memento if available
    try:
        ex_memento = AgentToolHttpMemento(**input.memento) if input.memento is not None else None
    except Exception as e:
        _log.warning(f"Failed to load memento: {e}")
        ex_memento = None
    
    # Get parameters
    url = input.params.url if input.params.url else ""
    validate = input.params.validate if hasattr(input.params, 'validate') else False
    health_check_path = input.params.health_check_path if hasattr(input.params, 'health_check_path') and input.params.health_check_path else ""
    headers = dict(input.params.headers) if hasattr(input.params, 'headers') and input.params.headers else {}
    timeout = input.params.timeout if hasattr(input.params, 'timeout') and input.params.timeout else 5
    
    # Validate required parameters
    if not url:
        markers.append(TaskMarker(
            msg="Parameter 'url' is required",
            severity=SeverityE.Error
        ))
        return TaskDataResult(status=1, markers=markers, changed=False)
    
    # Step 1: Validate URL format
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            markers.append(TaskMarker(
                msg=f"Invalid URL format: '{url}'. Must include scheme (http/https) and host.",
                severity=SeverityE.Error
            ))
            return TaskDataResult(status=1, markers=markers, changed=False)
        
        if parsed.scheme not in ['http', 'https']:
            markers.append(TaskMarker(
                msg=f"Unsupported URL scheme: '{parsed.scheme}'. Must be http or https.",
                severity=SeverityE.Error
            ))
            return TaskDataResult(status=1, markers=markers, changed=False)
    except Exception as e:
        markers.append(TaskMarker(
            msg=f"Failed to parse URL '{url}': {str(e)}",
            severity=SeverityE.Error
        ))
        return TaskDataResult(status=1, markers=markers, changed=False)
    
    _log.debug(f"URL format validated: {url}")
    
    # Step 2: Optional validation - check URL accessibility
    validation_timestamp = None
    
    if validate:
        _log.info(f"Validating URL accessibility: {url}")
        
        # Determine which URL to check
        check_url = url
        if health_check_path:
            check_url = urljoin(url, health_check_path)
            _log.debug(f"Using health check endpoint: {check_url}")
        
        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                async with session.get(check_url, headers=headers) as response:
                    if response.status >= 200 and response.status < 400:
                        _log.info(f"URL validation successful: status={response.status}")
                        import time
                        validation_timestamp = time.time()
                    else:
                        markers.append(TaskMarker(
                            msg=f"URL validation failed: HTTP {response.status}",
                            severity=SeverityE.Error
                        ))
                        # Read some of the response for debugging
                        try:
                            text = await response.text()
                            markers.append(TaskMarker(
                                msg=f"Response: {text[:200]}",
                                severity=SeverityE.Error
                            ))
                        except:
                            pass
                        return TaskDataResult(status=1, markers=markers, changed=False)
                        
        except aiohttp.ClientConnectorError as e:
            markers.append(TaskMarker(
                msg=f"Failed to connect to URL '{check_url}': {str(e)}",
                severity=SeverityE.Error
            ))
            markers.append(TaskMarker(
                msg=f"Ensure the server is running and accessible",
                severity=SeverityE.Error
            ))
            return TaskDataResult(status=1, markers=markers, changed=False)
        except asyncio.TimeoutError:
            markers.append(TaskMarker(
                msg=f"Request to '{check_url}' timed out after {timeout} seconds",
                severity=SeverityE.Error
            ))
            markers.append(TaskMarker(
                msg=f"Consider increasing timeout parameter or check server responsiveness",
                severity=SeverityE.Error
            ))
            return TaskDataResult(status=1, markers=markers, changed=False)
        except Exception as e:
            markers.append(TaskMarker(
                msg=f"Failed to validate URL '{check_url}': {str(e)}",
                severity=SeverityE.Error
            ))
            _log.exception("URL validation failed")
            return TaskDataResult(status=1, markers=markers, changed=False)
    else:
        _log.debug("URL validation skipped (validate=false)")
    
    # Step 3: Create URL hash for memento
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    
    # Check if configuration changed
    if ex_memento and ex_memento.url_hash != url_hash:
        changed = True
    elif not ex_memento:
        changed = True
    
    # Step 4: Create output data item
    if runner is not None:
        # Use runner.mkDataItem for proper type registration
        # Get task description from input
        task_desc = getattr(input, 'desc', '') or ''
        tool_data = runner.mkDataItem(
            "std.AgentTool",
            desc=task_desc,
            command="",
            args=[],
            url=url
        )
    else:
        # Fallback for unit tests without runner
        tool_data = AgentToolData(
            type="std.AgentTool",
            command="",
            args=[],
            url=url
        )
    
    output = [tool_data]
    
    # Step 5: Create memento
    memento = AgentToolHttpMemento(
        url_hash=url_hash,
        validation_timestamp=validation_timestamp
    )
    
    _log.info(f"AgentToolHttp configured: url={url}")
    
    return TaskDataResult(
        status=status,
        changed=changed,
        output=output,
        markers=markers,
        memento=memento
    )
