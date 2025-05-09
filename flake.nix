{
  description = "rvc2api Python package and DevShell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }@inputs:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python312;
        pythonPackages = pkgs.python312Packages;

        rvc2apiPackage = pythonPackages.buildPythonPackage {
          pname = "rvc2api";
          version = "0.1.0";
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

        # Local development shell with full tooling
        devShell = pkgs.mkShell {
          buildInputs = [
            python
            pkgs.poetry
            pythonPackages.fastapi
            pythonPackages.uvicorn
            pythonPackages.python-can
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

        # CI/CD shell: minimal but includes vcan0 setup
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

      in {
        packages.rvc2api = rvc2apiPackage;
        defaultPackage = self.packages.${system}.rvc2api;

        devShells.default = devShell;
        devShells.ci = ciShell;
      }
    );
}