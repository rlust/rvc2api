{
  description = "rvc2api Python package and DevShell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils"; # Helper for multi-system support
  };

  outputs = { self, nixpkgs, flake-utils, ... }@inputs:
    # Use flake-utils to simplify defining outputs for multiple systems
    flake-utils.lib.eachDefaultSystem (system:
      let
        # Package set for the current system
        pkgs = import nixpkgs { inherit system; };

        # Define the Python package build using Poetry
        rvc2apiPackage = pkgs.python3Packages.buildPythonPackage {
          pname = "rvc2api";
          version = "0.1.0"; # Ideally read from pyproject.toml, but explicit for now
          src = self; # Use the flake's own source tree

          # Build dependencies needed by the poetry build backend
          nativeBuildInputs = with pkgs.python3Packages; [ poetry-core ];

          # Runtime dependencies are now managed by Poetry and read from pyproject.toml
          # No need for propagatedBuildInputs here if Poetry handles it,
          # buildPythonPackage should infer them.

          format = "pyproject"; # This tells buildPythonPackage to use PEP 517

          propagatedBuildInputs = with pkgs.python3Packages; [
            fastapi
            uvicorn
            python-can
            pydantic
            pyyaml
            prometheus-client # Corrected: hyphenated
            coloredlogs
            jinja2
          ];

          # postInstall script is removed; Poetry should handle data files.
          # Ensure Python code uses importlib.resources or similar to access package data.

          # If you have tests defined in pyproject.toml that Nix can run:
          # doCheck = true; # You might need to configure how tests are run with Poetry
          # checkInputs = with pkgs.python3Packages; [ pytest ]; # Or let poetry handle it
        };

        # Helper to build a Python 3.12 shell
        mkPyShell = pkgs: let
          py     = pkgs.python312;
          pyPkgs = pkgs.python312Packages;
        in pkgs.mkShell {
          buildInputs = with pkgs; [
            py
            poetry # Add poetry CLI for managing the project
            # runtime deps (can be useful to have them in the shell directly)
            pyPkgs.fastapi
            pyPkgs.uvicorn
            pyPkgs.python-can
            pyPkgs.pydantic
            pyPkgs.pyyaml
            pyPkgs.coloredlogs
            pyPkgs.jinja2
            pyPkgs.prometheus_client # Added from previous propagatedBuildInputs
            # dev deps
            pyPkgs.pytest
            pyPkgs.mypy
            pyPkgs.flake8
            # Add the package itself to the dev shell for testing
            # rvc2apiPackage # This can be included if you want the Nix-built version
          ];
          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            # Advise user on Poetry usage
            echo "🐚 Entered rvc2api devShell on ${pkgs.system} (Python ${py.version})"
            echo "💡 Run 'poetry install' to set up the project's virtual environment."
            echo "💡 Then use 'poetry shell' or 'poetry run <command>'."
            echo "💡 The rvc2api package itself can be built by Nix (e.g., 'nix build .#')."
          '';
        };
      in
      {
        # Expose the package
        packages.default = rvc2apiPackage;

        # Keep the devShell
        devShells.default = mkPyShell pkgs;
      }
    );
}
