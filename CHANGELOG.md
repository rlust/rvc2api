# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.0.0 (2025-05-17)


### Features

* Add frontend build scripts for React application management ([3546b06](https://github.com/rlust/rvc2api/commit/3546b06e30934710160c2736eea5f1d1a6e4634b))
* Add type stubs for FastAPI and httpx to improve type checking and IDE support ([fac17d0](https://github.com/rlust/rvc2api/commit/fac17d0ee746a5d4d9c37fca73ad43c1302b33e7))
* Add VS Code configuration files for improved development setup ([7084ac4](https://github.com/rlust/rvc2api/commit/7084ac483ae58ebbc38a0e2c110cf0819cc0dee8))
* Enhance development environment and documentation for rvc2api ([9b74a65](https://github.com/rlust/rvc2api/commit/9b74a6519b784ef75afead294ada6a7da7b3137b))
* initialize web UI with React, Vite, and TypeScript ([3c8eb02](https://github.com/rlust/rvc2api/commit/3c8eb02cb0aceae14fa923a5728adbf00f8181d5))
* Standardize on Pyright for type checking (closes [#17](https://github.com/rlust/rvc2api/issues/17)) ([4bb3763](https://github.com/rlust/rvc2api/commit/4bb3763f60a6d8883384d7fdf70f9a5ee75235f7))
* Update GitHub Actions workflows for frontend CI and Nix-based CI with caching support ([b6cf007](https://github.com/rlust/rvc2api/commit/b6cf00743eefc2e40d31fe6b44c606572296d8ae))
* Update pre-commit configuration with additional hooks for mixed line endings and large file checks ([2095b22](https://github.com/rlust/rvc2api/commit/2095b2258c068d71880a8e1cd048cb3daae8876c))


### Bug Fixes

* Remove mypy type checking configuration from pre-commit setup ([5c037da](https://github.com/rlust/rvc2api/commit/5c037da2c3ea45a13edf186261e66903f43fcbcb))
* Standardize argument formatting and enhance mypy configuration with additional error codes ([90d0056](https://github.com/rlust/rvc2api/commit/90d0056f0d8acc418de9f99427883441bcf8ade4))

## [Unreleased]

### Added
- Initial release of rvc2api.
- FastAPI backend for API and WebSocket server.
- RV-C message decoding capabilities.
- Entity management for RV-C devices.
- Web UI for monitoring and control.
- Console client for direct interaction.
- Poetry for dependency management.
- Basic API and decoder tests.
