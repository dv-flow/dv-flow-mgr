###############
MCP Tool Support
###############

Overview
========

MCP (Model Context Protocol) enables AI agents to interact with external tools and 
services in a standardized way. DV Flow provides two task types for configuring 
MCP servers:

1. **AgentToolStdio**: For MCP servers using stdio transport (command-line tools)
2. **AgentToolHttp**: For MCP servers using HTTP/SSE transport (remote services)

Both tasks produce ``std.AgentTool`` data items that can be consumed by ``Agent`` 
tasks to enable additional capabilities during agent execution.

The AgentTool tasks configure how MCP servers should be started, but do not start 
them directly. The actual server processes are started by the Agent task or agent 
command when needed.

AgentToolStdio Task
===================

The ``AgentToolStdio`` task configures MCP servers that communicate via stdio 
(standard input/output). These are typically installed as npm or Python packages 
and run as subprocesses.

Parameters
----------

**command** (string, required)
    The command to execute the MCP server

**args** (list, optional)
    Command-line arguments to pass to the server

**install_command** (string, optional)
    Command to run before first use (e.g., ``npm install``)

**env** (map, optional)
    Environment variables to set when running the server

Basic Example
-------------

.. code-block:: yaml

    tasks:
      - name: FileSystemTool
        uses: std.AgentToolStdio
        with:
          command: npx
          args:
            - -y
            - "@modelcontextprotocol/server-filesystem"
            - /path/to/allowed/directory

      - name: MyAgent
        uses: std.Agent
        needs: [FileSystemTool]
        with:
          user_prompt: "List all Python files in the workspace"

With Installation Command
--------------------------

.. code-block:: yaml

    tasks:
      - name: FileSystemTool
        uses: std.AgentToolStdio
        with:
          command: npx
          args:
            - -y
            - "@modelcontextprotocol/server-filesystem"
            - /workspace
          install_command: "npm install -g @modelcontextprotocol/server-filesystem"
          env:
            NODE_ENV: production

With Environment Variables
---------------------------

.. code-block:: yaml

    tasks:
      - name: GitTool
        uses: std.AgentToolStdio
        with:
          command: npx
          args:
            - -y
            - "@modelcontextprotocol/server-git"
          env:
            GIT_CONFIG_GLOBAL: /custom/gitconfig

Common MCP Servers (Stdio)
---------------------------

=================== =============================================== ================================
Server              Package                                         Description
=================== =============================================== ================================
filesystem          @modelcontextprotocol/server-filesystem         Read/write files in directories
github              @modelcontextprotocol/server-github             GitHub API integration
sqlite              mcp-server-sqlite                               SQLite database queries
git                 @modelcontextprotocol/server-git                Git repository operations
fetch               @modelcontextprotocol/server-fetch              HTTP requests with caching
=================== =============================================== ================================

Implementation Details
----------------------

The ``AgentToolStdio`` task:

1. Optionally runs the ``install_command`` if specified and not previously executed
2. Validates that the command exists and is executable
3. Creates a memento with hash of command/args for up-to-date tracking
4. Outputs an ``std.AgentTool`` data item with command and args populated

The task does NOT start the MCP server itself - it only configures how to start it. 
The actual server process is started by the Agent task or agent command when needed.

Error Handling
--------------

**Command not found**
    Returns status=1 with error marker indicating the command could not be found

**Installation fails**
    Returns status=1 with error marker and stderr output from installation command

**Validation fails**
    Returns status=1 with error marker explaining the validation error

AgentToolHttp Task
==================

The ``AgentToolHttp`` task configures MCP servers that communicate via HTTP/SSE 
transport. These are typically remote services or locally-hosted HTTP servers.

Parameters
----------

**url** (string, required)
    The base URL of the MCP server

**validate** (bool, optional, default=false)
    Whether to validate that the URL is accessible

**health_check_path** (string, optional)
    Path to append to URL for health check

**headers** (map, optional)
    HTTP headers to include in requests (e.g., API keys)

**timeout** (int, optional, default=5)
    Timeout in seconds for validation requests

Basic Example
-------------

.. code-block:: yaml

    tasks:
      - name: LocalMCPServer
        uses: std.AgentToolHttp
        with:
          url: http://localhost:8080
          validate: false

      - name: MyAgent
        uses: std.Agent
        needs: [LocalMCPServer]
        with:
          user_prompt: "Query the local MCP server"

With Validation
---------------

.. code-block:: yaml

    tasks:
      - name: RemoteSearchTool
        uses: std.AgentToolHttp
        with:
          url: https://api.example.com/mcp
          validate: true
          timeout: 10

With Health Check and Headers
------------------------------

.. code-block:: yaml

    tasks:
      - name: RemoteAPI
        uses: std.AgentToolHttp
        with:
          url: https://api.example.com/mcp
          validate: true
          health_check_path: /health
          headers:
            Authorization: "Bearer ${API_KEY}"
            X-API-Version: "v1"
          timeout: 15

Implementation Details
----------------------

The ``AgentToolHttp`` task:

1. Validates the URL format
2. Optionally performs accessibility check if ``validate=true``
3. Optionally performs health check if ``health_check_path`` is specified
4. Creates a memento with hash of URL for up-to-date tracking
5. Outputs an ``std.AgentTool`` data item with url populated

Like ``AgentToolStdio``, this task only configures the connection - it does not 
establish or maintain the connection. The Agent task handles the actual HTTP/SSE 
communication.

Error Handling
--------------

**Invalid URL format**
    Returns status=1 with error marker if URL is malformed or missing scheme/host

**Connection failed**
    Returns status=1 with error marker if validation is enabled and URL is unreachable

**Health check failed**
    Returns status=1 with error marker and HTTP status code if health check fails

**Timeout**
    Returns status=1 with error marker if request times out

Integration with Agent Tasks
=============================

The Agent task (and agent command) automatically discovers AgentTool data items 
from upstream tasks through the context builder. The workflow is:

1. User defines AgentToolStdio or AgentToolHttp tasks
2. Agent task declares dependency on these tasks (via ``needs``)
3. Context builder extracts tool configuration from task results
4. Agent runtime configures MCP client with extracted tools
5. AI assistant can use MCP tools during execution

Context Builder Integration
----------------------------

The ``context_builder.py`` module extracts AgentTool data from executed tasks:

.. code-block:: python

    def _extract_tool(self, task, task_node) -> Optional[Dict[str, Any]]:
        """Extract tool/MCP server information from task."""
        tool = {
            'name': task.name,
            'desc': getattr(task, 'desc', '') or '',
            'command': '',  # For stdio
            'args': [],     # For stdio
            'url': ''       # For HTTP
        }
        # Extract from task output...
        return tool

The extracted tools are included in the AgentContext and passed to the AI 
assistant's MCP client configuration.

Complete Example Workflow
==========================

.. code-block:: yaml

    package:
      name: my_project
      
    tasks:
      # Configure filesystem access tool
      - name: FileSystemAccess
        uses: std.AgentToolStdio
        with:
          command: npx
          args:
            - -y
            - "@modelcontextprotocol/server-filesystem"
            - /workspace
      
      # Configure remote API tool
      - name: ExternalAPI
        uses: std.AgentToolHttp
        with:
          url: https://api.example.com/mcp
          validate: true
          headers:
            Authorization: "Bearer ${API_KEY}"
      
      # Agent that uses both tools
      - name: CodeAnalyzer
        uses: std.Agent
        needs: [FileSystemAccess, ExternalAPI]
        with:
          user_prompt: |
            Analyze all Python files in the workspace and check 
            them against the external API for best practices.
          result_file: analysis.json

When ``CodeAnalyzer`` runs:

1. Both tool tasks execute first (due to ``needs`` dependency)
2. Context builder extracts tool configurations
3. Agent runtime starts filesystem MCP server as subprocess
4. Agent runtime configures HTTP client for external API
5. AI assistant can use both tools to complete the analysis

Testing MCP Tool Tasks
=======================

Unit Testing
------------

Unit tests mock external dependencies:

.. code-block:: python

    # Test AgentToolStdio
    async def test_agent_tool_stdio_basic(mock_subprocess):
        input = create_mock_input(command="node", args=["server.js"])
        result = await AgentToolStdio(mock_runner, input)
        
        assert result.status == 0
        assert len(result.output) == 1
        assert result.output[0].type == "std.AgentTool"
        assert result.output[0].command == "node"

    # Test AgentToolHttp
    async def test_agent_tool_http_validation(mock_requests):
        mock_requests.get.return_value.status_code = 200
        input = create_mock_input(url="http://localhost:8080", validate=True)
        result = await AgentToolHttp(mock_runner, input)
        
        assert result.status == 0
        assert result.output[0].url == "http://localhost:8080"

Integration Testing
-------------------

Integration tests use real MCP servers:

.. code-block:: python

    async def test_agent_with_filesystem_tool():
        # Create flow with AgentToolStdio and Agent tasks
        # Execute flow
        # Verify agent can access filesystem via MCP
        # Check that files were read/written as expected

Troubleshooting
===============

AgentToolStdio Issues
---------------------

**Problem: Command not found**

Solutions:
    - Ensure command is in PATH or use absolute path
    - Use ``install_command`` to install dependencies first

**Problem: Permission denied**

Solutions:
    - Check file permissions on command
    - Ensure rundir has write permissions

**Problem: Server fails to start**

Solutions:
    - Check command arguments are correct
    - Review server logs in task rundir

AgentToolHttp Issues
--------------------

**Problem: URL unreachable**

Solutions:
    - Check network connectivity
    - Verify URL format and port
    - Ensure server is running if local

**Problem: Authentication failures**

Solutions:
    - Check headers are correctly specified
    - Verify API keys are valid and not expired

**Problem: Timeout errors**

Solutions:
    - Increase timeout parameter
    - Check server response time

Best Practices
==============

Organization
------------

**Keep tools focused**
    Each tool should have a single, clear purpose

**Use descriptive names**
    Name tools based on their function, not their implementation

**Document limitations**
    Clearly document any restrictions or requirements

Configuration
-------------

**Use environment variables**
    Pass sensitive data through environment variables, not command arguments

**Set appropriate timeouts**
    Balance between reliability and responsiveness

**Enable validation in development**
    Use ``validate: true`` during development, consider disabling in production

**Install once**
    Use ``install_command`` with mementos to avoid redundant installations

Security
--------

**Restrict filesystem access**
    Limit filesystem tools to specific directories

**Validate API endpoints**
    Use ``validate: true`` and ``health_check_path`` for remote services

**Protect credentials**
    Never hardcode API keys; use environment variables or parameter substitution

**Review tool permissions**
    Understand what each MCP server can access

See Also
========

* :doc:`agent_integration` - AI Agent Integration guide
* :doc:`llm_integration` - LLM Integration overview
* :doc:`../llms` - LLM Agent Integration reference
* :doc:`tasks_developing` - Developing custom tasks
