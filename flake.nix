{
  description = "rvc2api Python package and DevShell";

  inputs = {
    # Pin nixpkgs to the same commit as rv-nixpi
    nixpkgs.url     = "github:NixOS/nixpkgs/5b35d248e9206c1f3baf8de6a7683fee126364aa";
    flake-utils.url = "github:numtide/flake-utils";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs"; # Ensure poetry2nix also uses the pinned version
    };
  };

  outputs = { self, nixpkgs, flake-utils, poetry2nix, ... }@inputs:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ inputs.poetry2nix.overlays.default ]; # Use inputs.poetry2nix.overlays.default
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
