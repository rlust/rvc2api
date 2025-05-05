{
  description = "DevShell for rvc2api";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  };

  outputs = { self, nixpkgs, ... }:
  let
    pkgs_x86_64   = import nixpkgs { system = "x86_64-linux"; };
    pkgs_aarch64  = import nixpkgs { system = "aarch64-darwin"; };

    commonDeps = xs: [
      xs.python39
      xs.python39Packages.setuptools
      xs.python39Packages.wheel
      xs.python39Packages.fastapi
      xs.python39Packages.uvicorn
      xs.python39Packages.python-can
      xs.python39Packages.pydantic
      xs.python39Packages.pytest
      xs.python39Packages.mypy
      xs.python39Packages.flake8
    ];
  in {
    devShells = {
      "x86_64-linux" = {
        default = pkgs_x86_64.mkShell {
          buildInputs = commonDeps pkgs_x86_64;
          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            echo "🐚 rvc2api devShell (x86_64-linux)"
          '';
        };
      };

      "aarch64-darwin" = {
        default = pkgs_aarch64.mkShell {
          buildInputs = commonDeps pkgs_aarch64;
          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            echo "🐚 rvc2api devShell (aarch64-darwin)"
          '';
        };
      };
    };
  };
}
