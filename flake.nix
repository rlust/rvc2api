{
  description = "DevShell for rvc2api (Python 3.13)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  };

  outputs = { self, nixpkgs, ... }:
  let
    # Package sets per host
    pkgs_x86_64   = import nixpkgs { system = "x86_64-linux"; };
    pkgs_aarch64  = import nixpkgs { system = "aarch64-darwin"; };

    # Helper to build a Python 3.13 shell
    mkPyShell = pkgs: let
      py     = pkgs.python313;
      pyPkgs = pkgs.python313Packages;
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
        # dev deps
        pyPkgs.pytest
        pyPkgs.mypy
        pyPkgs.flake8
      ];
      shellHook = ''
        export PYTHONPATH=$PWD/src:$PYTHONPATH
        echo "🐚 Entered rvc2api devShell on ${pkgs.system} (Python ${py.version})"
      '';
    };
  in {
    devShells = {
      "x86_64-linux"   = { default = mkPyShell pkgs_x86_64; };
      "aarch64-darwin" = { default = mkPyShell pkgs_aarch64; };
    };
  };
}
