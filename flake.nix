{
  description = "rvc2api Python package and DevShell";

  inputs = {
    # Use nixos-unstable branch
    nixpkgs.url     = "nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs"; # Ensure poetry2nix also uses unstable
    };
  };

  outputs = { self, nixpkgs, flake-utils, poetry2nix, ... }@inputs:
    flake-utils.lib.eachDefaultSystem (system:
      let
        # Overlay to fix fastapi-cli dependency issue if present in current unstable
        fixFastapiCliOverlay = final: super: {
          python3Packages = super.python3Packages.overrideScope (pyfinal: pysuper: {
            fastapi-cli = pysuper.fastapi-cli.overridePythonAttrs (old: {
              # Redefine propagatedBuildInputs completely to avoid evaluating the original problematic expression
              propagatedBuildInputs = with pyfinal; [ 
                click
                fastapi
                jinja2
                pydantic
                python-multipart
                pyyaml
                shellingham
                toml
                typer
                uvicorn
              ];
            });
          });
        };

        pkgs = import nixpkgs {
          inherit system;
          overlays = [ inputs.poetry2nix.overlays.default fixFastapiCliOverlay ]; # Apply overlays
        };
      in {
        # Build your application entirely from pyproject.toml + poetry.lock
        packages.default = pkgs.poetry2nix.mkPoetryApplication {
          projectDir = ./.;
        };

        # A devShell with all runtime + dev deps and your project on PYTHONPATH
        devShells.default = pkgs.poetry2nix.mkPoetryShell {
          projectDir = ./.;
        };
      }
    );
}
