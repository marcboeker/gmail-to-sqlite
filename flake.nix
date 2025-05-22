{
  inputs = {
    utils.url = "github:numtide/flake-utils";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };


    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

  };
  outputs = { self, nixpkgs, utils, pyproject-nix, uv2nix, pyproject-build-systems }: utils.lib.eachDefaultSystem (system:
    let
      inherit (nixpkgs) lib;

      pkgs = nixpkgs.legacyPackages.${system};

      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };


      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };

      pyprojectOverrides = final: prev: {
        bs4 = prev.bs4.overrideAttrs (old:{
          nativeBuildInputs = old.nativeBuildInputs ++ [
            (final.resolveBuildSystem {
              setuptools = [];

            })
          ];
        });
        peewee = prev.peewee.overrideAttrs (old:{
          nativeBuildInputs = old.nativeBuildInputs ++ [
            (final.resolveBuildSystem {
              setuptools = [];
            })
          ];
        });
      };

      
      python = pkgs.python313;

      uvWrapped = pkgs.stdenv.mkDerivation {
        name = "uv-wrapped";
        nativeBuildInputs = [pkgs.makeWrapper];
        buildCommand = if pkgs.stdenv.isLinux then ''
        mkdir $out
        makeWrapper ${pkgs.uv}/bin/uv $out/bin/uv \
        --prefix UV_PYTHON_DOWNLOADS : "never" \
        --prefix UV_PYTHON : "${python.interpreter}" \
        --prefix LD_LIBRARY_PATH : "${lib.makeLibraryPath pkgs.pythonManylinuxPackages.manylinux1}"
        '' else ''
        mkdir $out
        makeWrapper ${pkgs.uv}/bin/uv $out/bin/uv \
        --prefix UV_PYTHON_DOWNLOADS : "never" \
        --prefix UV_PYTHON : "${python.interpreter}"
        '';
      };

      pythonSet =
        # Use base package set from pyproject.nix builders
        (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope
          (
            pkgs.lib.composeManyExtensions [ 
              pyproject-build-systems.overlays.default
              overlay 
              pyprojectOverrides
            ]
            );

        inherit (pkgs.callPackages pyproject-nix.build.util { }) mkApplication;
    in
    {
      packages.venv = pythonSet.mkVirtualEnv "mail-to-sqlite" workspace.deps.default;

      packages.default = mkApplication {
        venv = self.packages.${system}.venv;
        package = pythonSet.mail-to-sqlite;
      };

      devShell = pkgs.mkShell {
        buildInputs = with pkgs; [
          uvWrapped
        ];
      };
    }
  );
}
