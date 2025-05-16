---
applyTo: "**"
---

# Model Context Protocol (MCP) Tools

> **Note**: This file provides an overview of MCP tools for the project. For domain-specific examples, see the tool recommendation sections in the respective instruction files (code-style, testing, env-vars, react-frontend).

MCP tools provide context-aware AI assistance. They are integrated into GitHub Copilot Chat and can help you understand the codebase, research related topics, and navigate project repositories.

## Overview of Available Tools

### @context7
Project-aware code lookups that analyze the rvc2api codebase:

- **Core functionality**: Find implementations, understand patterns, and reference API schemas
- **When to use**: When you need to understand existing code or find examples in the codebase

### @perplexity
External research for protocols, libraries, and best practices:

- **Core functionality**: Search the web for technical information relevant to your task
- **When to use**: When you need information not found in the codebase (protocols, libraries, techniques)

### @github
Repository and issue information queries:

- **Core functionality**: Search repositories, issues, pull requests, and documentation
- **When to use**: To find related issues, check project history, or reference GitHub resources

## @github Examples

```
# Search for issues related to WebSocket reconnection
@github issues:rvc2api+websocket+reconnection

# Find pull requests related to the React migration
@github pr:rvc2api+react+frontend

# Get repository statistics
@github repo:rvc2api stats

# Search for code examples in related repositories
@github code:python-can+socketcan+send
```

## Integrated Research Workflow

For most development tasks, follow this pattern:

1. **Explore the codebase**: Use `@context7` to find relevant code patterns
   ```
   @context7 similar functionality to what I'm building
   ```

2. **Research external information**: Use `@perplexity` to find best practices
   ```
   @perplexity technical approach for solving this problem
   ```

3. **Check project history**: Use `@github` to find related issues/PRs
   ```
   @github issues related to this component
   ```

4. **Document your sources**: Reference findings in code comments and PR descriptions
