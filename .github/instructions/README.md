# GitHub Copilot Instructions

This directory contains modular GitHub Copilot instructions for the `rvc2api` project. Each file includes YAML frontmatter with an `applyTo` pattern indicating which files the instructions apply to.

## Available Instructions

| File | Applies To | Description |
|------|------------|-------------|
| [project-overview.instructions.md](project-overview.instructions.md) | All files | Project architecture and structure |
| [code-style.instructions.md](code-style.instructions.md) | Python files | Coding standards and documentation |
| [testing.instructions.md](testing.instructions.md) | Test files | Test patterns and requirements |
| [webui.instructions.md](webui.instructions.md) | Web UI files | Frontend template and JS standards |
| [env-vars.instructions.md](env-vars.instructions.md) | Python files | Configuration and environment setup |
| [dev-environment.instructions.md](dev-environment.instructions.md) | All files | Setting up and using dev tools |
| [mcp-tools.instructions.md](mcp-tools.instructions.md) | All files | Using Copilot Chat tools (@context7, etc.) |
| [pull-requests.instructions.md](pull-requests.instructions.md) | All files | PR guidelines and expectations |

## Using These Instructions

These files are designed to work with GitHub Copilot in VS Code. When editing a file, GitHub Copilot will automatically apply the relevant instructions based on the file type.

You can also use the prompt templates in the [../prompts](../prompts) directory for more specific guidance on common development tasks.
