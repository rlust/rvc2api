{
  description = "DevShell for rvc2api";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  };

  outputs = { self, nixpkgs, ... }:
    let
      # detect the host system (e.g. "x86_64-linux" or "aarch64-darwin")
      system = builtins.currentSystem;
      # import the corresponding package set
      pkgs   = import nixpkgs { inherit system; };
    in {
      # define a single default devShell that works on any host
      devShells = {
        default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python39
            python39Packages.setuptools
            python39Packages.wheel
            python39Packages.fastapi
            python39Packages.uvicorn
            python39Packages.python-can
            python39Packages.pydantic
            python39Packages.pytest
            python39Packages.mypy
            python39Packages.flake8
          ];
          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            echo "🐚 Entered rvc2api devShell on ${system}"
          '';
        };
      };
    };
}
