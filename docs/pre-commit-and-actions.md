# Pre-commit and GitHub Actions Configuration

This document describes the enhanced pre-commit and GitHub Actions configuration for the `rvc2api` project.

## Pre-commit Configuration

The project uses [pre-commit](https://pre-commit.com/) to enforce code quality standards before commits. This ensures consistent code formatting and catches common issues early.

### Installed Hooks

The pre-commit configuration includes:

1. **Core file checks**:

   - Trailing whitespace removal
   - End-of-file fixer
   - YAML/JSON/TOML validation
   - Merge conflict detection
   - Debug statement detection
   - Line ending normalization
   - Large file checks

2. **Python code quality**:

   - **Black**: Code formatting
   - **Ruff**: Modern Python linting (replaces Flake8)
   - **Pyright**: Type checking (see `pyrightconfig.json` and `pyproject.toml`)

3. **Frontend code quality**:

   - **ESLint**: JavaScript/TypeScript linting
   - **djLint**: HTML template linting

4. **Project integrity**:
   - Poetry lock file validation

### Using Pre-commit

```bash
# Install pre-commit hooks
poetry run pre-commit install

# Run against all files
poetry run pre-commit run --all-files

# Run a specific hook
poetry run pre-commit run black --all-files
```

## GitHub Actions Configuration

The project uses GitHub Actions to automate CI/CD processes.

### Available Workflows

1. **Nix-based CI** (`nix-ci.yml`):

   - Runs all pre-commit checks
   - Executes all tests
   - Validates Poetry lock file
   - Builds the project with Nix

2. **Frontend CI** (`frontend.yml`):

   - Triggered by changes to the `web_ui` directory
   - Runs linting and type checking
   - Builds the frontend
   - Uploads build artifacts

3. **Dependency Validation** (`nixpkgs-version-check.yml`):

   - Checks that Python dependencies are available in Nixpkgs
   - Triggered by changes to Poetry configuration

4. **Release Management** (`release-please.yml`):
   - Automates version bumping and release notes
   - Creates release pull requests

## Local Development

For day-to-day development, you can use VS Code tasks to run common operations:

- **Start Backend Server**: Run the FastAPI server
- **Start Frontend Dev Server**: Run the Vite development server
- **Run Tests**: Execute pytest
- **Format Code**: Run Black formatter
- **Lint (Ruff)**: Run Ruff linter
- **Build Frontend**: Create production frontend build

## Adding New Checks

To add new checks to the pre-commit configuration:

1. Add the hook to `.pre-commit-config.yaml`
2. Update the Ruff configuration in `pyproject.toml` if needed
3. Update GitHub Actions workflows if additional CI steps are needed
