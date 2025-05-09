# flake.nix — Nix flake definition for rvc2api
#
# This flake provides:
#
# ▸ A Python-based CANbus FastAPI web service built with Poetry
# ▸ Unified versioning via the root-level `VERSION` file
# ▸ Reproducible developer environments with `devShells.default` and `devShells.ci`
# ▸ CLI apps (run with `nix run .#<name>`) for:
#    - `test`     → run unit tests
#    - `lint`     → run flake8, mypy, djlint
#    - `format`   → run black and djlint in reformat mode
#    - `check`    → run full gate: pre-commit, tests, lints, poetry lock
#    - `precommit`→ run pre-commit checks across the repo
# ▸ Nix flake checks (via `nix flake check`) for:
#    - pytest suite
#    - style (flake8, mypy, djlint)
#    - lockfile validation (poetry lock --check)
# ▸ Package build output under `packages.<system>.rvc2api`
#
# Best Practices:
# - Canonical version is managed in `VERSION`
# - `pyproject.toml` is pinned to version "0.0.0"
# - Release automation is handled via `release-please`, which updates `VERSION` and `flake.nix`
# - Runtime version is available in the app via `core_daemon._version.VERSION`
#
# Usage (in this repo):
#   nix develop             # Enter the default dev environment
#   nix run .#test          # Run tests
#   nix run .#lint          # Run linter suite
#   nix flake check         # Run CI-grade validation
#   nix build .#rvc2api     # Build the package
#
# Usage (in a system flake or NixOS configuration):
#
#   # In your flake inputs:
#   inputs.rvc2api.url = "github:carpenike/rvc2api";
#
#   # In your systemPackages or services:
#   environment.systemPackages = [ inputs.rvc2api.packages.${system}.rvc2api ];
#
#   # Or to reference CLI apps:
#   nix run inputs.rvc2api#check

{
  description = "rvc2api Python package and DevShell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python312;
        pythonPackages = pkgs.python312Packages;

        version = builtins.replaceStrings ["\n"] [""] (builtins.readFile ./VERSION);

        rvc2apiPackage = pythonPackages.buildPythonPackage {
          pname = "rvc2api";
          inherit version;
          src = self;
          format = "pyproject";

          nativeBuildInputs = with pythonPackages; [ poetry-core ];
          propagatedBuildInputs = with pythonPackages; [
            fastapi
            uvicorn
            python-can
            pydantic
            pyyaml
            prometheus_client
            coloredlogs
            jinja2
          ];

          doCheck = true;
          checkInputs = with pythonPackages; [ pytest ];

          meta = with pkgs.lib; {
            description = "CAN‑bus web service exposing RV‑C network data via HTTP & WebSocket";
            homepage = "https://github.com/carpenike/rvc2api";
            license = licenses.asl20;
            maintainers = [{
              name = "Ryan Holt";
              email = "ryan@ryanholt.net";
              github = "carpenike";
            }];
          };
        };

        devShell = pkgs.mkShell {
          buildInputs = [
            python
            pkgs.poetry
            pythonPackages.fastapi
            pythonPackages.uvicorn
            pythonPackages."python‑can"
            pythonPackages.pydantic
            pythonPackages.pyyaml
            pythonPackages.prometheus_client
            pythonPackages.coloredlogs
            pythonPackages.jinja2
            pythonPackages.pytest
            pythonPackages.mypy
            pythonPackages.flake8
            pythonPackages.types-pyyaml
          ];
          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            echo "🐚 Entered rvc2api devShell on ${pkgs.system} with Python ${python.version}"
            echo "💡 Run 'poetry install' or 'nix build .#rvc2api' to get started."
          '';
        };

        ciShell = pkgs.mkShell {
          buildInputs = [
            python
            pkgs.poetry
            pythonPackages.pytest
            pythonPackages.pyyaml
            pkgs.can-utils
            pkgs.iproute2
          ];
          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            echo "🧪 Entered CI shell for rvc2api with vcan support"

            if [ "$(uname)" = "Linux" ] && command -v sudo >/dev/null; then
              echo "⚙️  Setting up virtual CAN interface (vcan0)..."
              sudo modprobe vcan || true
              sudo ip link add dev vcan0 type vcan || true
              sudo ip link set up vcan0 || true
            fi
          '';
        };

        apps = {
          precommit = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "precommit";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                poetry install --no-root
                poetry run pre-commit run --all-files
              '';
            };
          };

          test = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "test";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                poetry install --no-root
                poetry run pytest
              '';
            };
          };

          lint = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "lint";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                poetry install --no-root
                poetry run flake8
                poetry run mypy src
                poetry run djlint src/core_daemon/web_ui/templates --check
              '';
            };
          };

          format = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "format";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                poetry install --no-root
                poetry run black src
                poetry run djlint src/core_daemon/web_ui/templates --reformat
              '';
            };
          };

          check = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "check";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                poetry install --no-root
                poetry lock --check
                poetry run pre-commit run --all-files
                poetry run pytest
                poetry run flake8
                poetry run mypy src
                poetry run djlint src/core_daemon/web_ui/templates --check
              '';
            };
          };
        };

        checks = {
          pytest = pkgs.runCommand "pytest" {
            src = ./.;
            buildInputs = [ pkgs.poetry python ];
          } ''
            cd $src
            export POETRY_VIRTUALENVS_IN_PROJECT=false
            export POETRY_VIRTUALENVS_PATH="$TMPDIR/venvs"
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            poetry install --no-root
            poetry run pytest
            touch $out
          '';

          flake8 = pkgs.runCommand "flake8" {
            src = ./.;
            buildInputs = [ pkgs.poetry python ];
          } ''
            cd $src
            export POETRY_VIRTUALENVS_IN_PROJECT=false
            export POETRY_VIRTUALENVS_PATH="$TMPDIR/venvs"
            poetry install --no-root
            poetry run flake8
            touch $out
          '';

          mypy = pkgs.runCommand "mypy" {
            src = ./.;
            buildInputs = [ pkgs.poetry python ];
          } ''
            cd $src
            export POETRY_VIRTUALENVS_IN_PROJECT=false
            export POETRY_VIRTUALENVS_PATH="$TMPDIR/venvs"
            poetry install --no-root
            poetry run mypy src
            touch $out
          '';

          djlint = pkgs.runCommand "djlint" {
            src = ./.;
            buildInputs = [ pkgs.poetry python ];
          } ''
            cd $src
            export POETRY_VIRTUALENVS_IN_PROJECT=false
            export POETRY_VIRTUALENVS_PATH="$TMPDIR/venvs"
            poetry install --no-root
            poetry run djlint src/core_daemon/web_ui/templates --check
            touch $out
          '';

          poetry-lock-check = pkgs.runCommand "poetry-lock-check" {
            src = ./.;
            buildInputs = [ pkgs.poetry python ];
          } ''
            cd $src
            export POETRY_VIRTUALENVS_IN_PROJECT=false
            export POETRY_VIRTUALENVS_PATH="$TMPDIR/venvs"
            poetry lock --check
            touch $out
          '';
        };
      in {
        packages.rvc2api = rvc2apiPackage;
        defaultPackage = self.packages.${system}.rvc2api;

        devShells.default = devShell;
        devShells.ci = ciShell;

        inherit apps checks;
      }
    );
}
