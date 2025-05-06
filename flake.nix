{
  description = "rvc2api Python package and DevShell";

  inputs = {
    nixpkgs.url     = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    poetry2nix.url  = "github:nix-community/poetry2nix";
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
