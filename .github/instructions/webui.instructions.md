---
applyTo: "src/core_daemon/web_ui/**"
---

# Legacy Web UI Guidelines

> **Note**: This file describes the legacy template-based web UI.
> The project has been refactored to use a React frontend in the `web_ui/` directory.
> For React development, please refer to [react-frontend.instructions.md](react-frontend.instructions.md).

- HTML templates: `src/core_daemon/web_ui/templates/` (legacy)
- Static files: `src/core_daemon/web_ui/static/` (legacy)
- Format templates with `djlint`
- Use ES6 and JSDoc in custom JavaScript

> This has now been migrated to `web_ui/` with React + Vite.

## JavaScript Style

- Use ES6 features (arrow functions, destructuring, etc.)
- Add JSDoc comments for functions and complex logic
- Follow consistent naming: camelCase for variables and functions

## HTML Templates

- Use semantic HTML5 elements
- Keep templates modular and focused
- Include data attributes for JavaScript hooks (e.g., `data-action="toggle"`)

## CSS/Tailwind

- Follow BEM naming convention for custom CSS
- Prefer utility classes from Tailwind when available
- Maintain responsive design patterns
