---
applyTo: "src/core_daemon/web_ui/**"
---

# Web UI Guidelines (Pre-Refactor)

- HTML templates: `src/core_daemon/web_ui/templates/`
- Static files: `src/core_daemon/web_ui/static/`
- Format templates with `djlint`
- Use ES6 and JSDoc in custom JavaScript

> This will later migrate to `webui/` with React + Vite.

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
