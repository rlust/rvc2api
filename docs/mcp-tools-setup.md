# MCP Tools Setup and Management for rvc2api

This guide explains how to set up and manage [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools for the rvc2api project. These tools provide context-aware AI assistance through GitHub Copilot Chat.

## Available MCP Tools

The project utilizes three primary MCP tools:

1. **@context7**: Provides project-aware code lookups
2. **@perplexity**: Offers external research capabilities
3. **@github**: Enables repository and issue information queries

## Setting Up MCP Tools

### Prerequisites

- VS Code with GitHub Copilot and GitHub Copilot Chat extensions
- Required MCP server extensions installed

### Installation

Install the necessary VS Code extensions:

- GitHub Copilot
- GitHub Copilot Chat
- Relevant MCP extensions:
  - Context7 Extension (for @context7)
  - GitHub Extension (for @github)
  - Perplexity Extension (for @perplexity)

## Using VS Code Tasks for MCP Tools

The project includes VS Code tasks for managing MCP tools:

### Starting/Restarting MCP Servers

1. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on macOS)
2. Select "Tasks: Run Task"
3. Choose "Restart MCP - context7 Server"

### Checking MCP Tool Status

1. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on macOS)
2. Select "Tasks: Run Task"
3. Choose "MCP Tools Status"

## Using MCP Tools in Development

### @context7 Examples

```
# Find implementations of WebSocket handling
@context7 WebSocket connection handling

# Learn about CANbus integration
@context7 python-can integration

# Understand API routes
@context7 FastAPI route implementation
```

### @perplexity Examples

```
# Research external technologies
@perplexity RV-C protocol specification

# Find best practices
@perplexity FastAPI dependency injection patterns

# Explore alternative libraries
@perplexity python-can vs socketcan-python
```

### @github Examples

```
# Search for issues
@github issues:rvc2api+websocket+reconnection

# Find pull requests
@github pr:rvc2api+react+frontend

# Get repository statistics
@github repo:rvc2api stats
```

## Troubleshooting

### Common Issues

1. **MCP Server Not Responding**

   - Use the "Restart MCP - context7 Server" task
   - Check if the server process is running with "MCP Tools Status"
   - Restart VS Code

2. **Limited or Outdated Context**

   - The context server might need to re-index your codebase
   - Try running the indexing command manually or restart the server

3. **External Research Failing**
   - Check your internet connection
   - Verify API keys or authentication if applicable

## Advanced Configuration

For advanced configuration of MCP tools, refer to the specific documentation for each tool:

- [Context7 Documentation](https://context7.ai/)
- [GitHub Copilot Documentation](https://docs.github.com/en/copilot)
- [Perplexity Documentation](https://www.perplexity.ai/)
