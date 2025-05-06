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

        # Define the Python package build
        rvc2apiPackage = pkgs.python3Packages.buildPythonPackage {
          pname = "rvc2api";
          version = "0.1.0"; # Read from pyproject.toml ideally, but explicit for now
          src = self; # Use the flake's own source tree

          # Build dependencies needed by setuptools/build backend
          buildInputs = with pkgs.python3Packages; [ setuptools wheel ];

          # Runtime dependencies (Nix usually gets these from pyproject.toml)
          # propagatedBuildInputs = with pkgs.python3Packages; [ fastapi uvicorn python-can pydantic pyyaml ];

          format = "pyproject";

          # Include package data (config files)
          # This might require adjustments based on how setuptools handles it
          postInstall = ''
            mkdir -p $out/lib/${pkgs.python3.libPrefix}/site-packages/rvc_decoder/config
            cp src/rvc_decoder/config/* $out/lib/${pkgs.python3.libPrefix}/site-packages/rvc_decoder/config/
          '';

          # If you have tests defined in pyproject.toml that Nix can run:
          # doCheck = true;
          # checkInputs = with pkgs.python3Packages; [ pytest ];
        };

        # Helper to build a Python 3.12 shell (kept for development)
        mkPyShell = pkgs: let
          py     = pkgs.python312;
          pyPkgs = pkgs.python312Packages;
        in pkgs.mkShell {
          buildInputs = with pkgs; [
            py
            # core tooling
            pyPkgs.setuptools
            pyPkgs.wheel
            # runtime deps
            pyPkgs.fastapi
            pyPkgs.uvicorn
            pyPkgs.python-can
            pyPkgs.pydantic
            pyPkgs.pyyaml
            # dev deps
            pyPkgs.pytest
            pyPkgs.mypy
            pyPkgs.flake8
            # Add the package itself to the dev shell for testing
            rvc2apiPackage
          ];
          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            echo "🐚 Entered rvc2api devShell on ${pkgs.system} (Python ${py.version}) - Package: ${rvc2apiPackage}"
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
