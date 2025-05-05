{
  description = "DevShell for rvc2api";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  };

  outputs = { self, nixpkgs, ... }:
    let
      system = "x86_64-linux";   # or "aarch64-linux" on your Pi
      pkgs   = nixpkgs.legacyPackages.${system};
    in {
      devShells.${system}.default = pkgs.mkShell {
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
        # optional: set your PYTHONPATH so your editable install works
        shellHook = ''
          export PYTHONPATH=$PWD/src:$PYTHONPATH
        '';
      };
    };
}
