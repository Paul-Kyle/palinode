{
  description = "Palinode — persistent long-term memory for AI agents";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      # NixOS module — available on all systems (not system-specific)
      nixosModules = {
        palinode = import ./nix/services/palinode-service.nix;
        palinode-mcp = import ./nix/services/mcp-service.nix;
      };
    in
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python311;

        # Runtime dependencies from pyproject.toml [project.dependencies]
        # A few packages may not yet be in nixpkgs — marked with TODO for community contributors.
        propagatedBuildInputs = with python.pkgs; [
          # TODO: add sqlite-vec — not yet in nixpkgs; track https://github.com/NixOS/nixpkgs/pulls
          watchdog
          pyyaml
          httpx
          # TODO: add python-frontmatter — check nixpkgs as "python3Packages.python-frontmatter" or "frontmatter"
          fastapi
          uvicorn
          pydantic
          # TODO: add mcp — Model Context Protocol SDK; track https://github.com/NixOS/nixpkgs/pulls
          rich
          click
        ];

        devDeps = with python.pkgs; [
          pytest
          pytestAsyncio
          pip
        ];

        palinodePackage = python.pkgs.buildPythonApplication {
          pname = "palinode";
          version = "0.8.0";
          format = "pyproject";

          src = ./.;

          nativeBuildInputs = with python.pkgs; [
            setuptools
            wheel
          ];

          inherit propagatedBuildInputs;

          # Entry points defined in pyproject.toml [project.scripts]:
          #   palinode            → palinode.cli:main
          #   palinode-api        → palinode.api.server:main
          #   palinode-mcp        → palinode.mcp:main
          #   palinode-mcp-http   → palinode.mcp:main_http
          #   palinode-mcp-sse    → palinode.mcp:main_sse  (deprecated alias)
          #   palinode-watcher    → palinode.indexer.watcher:main

          # Skip the default check phase until sqlite-vec and mcp are in nixpkgs
          doCheck = false;

          meta = with pkgs.lib; {
            description = "The memory substrate for AI agents and developer tools. Git-versioned, file-native, MCP-first.";
            homepage = "https://github.com/phasespace-labs/palinode";
            license = licenses.mit;
            maintainers = [ ];
          };
        };

      in
      {
        packages = {
          default = palinodePackage;
          palinode = palinodePackage;
        };

        devShells.default = pkgs.mkShell {
          packages = [
            python
            python.pkgs.pip
          ] ++ propagatedBuildInputs ++ devDeps;

          shellHook = ''
            echo "palinode dev shell — Python $(python --version)"
            echo "Run: pip install -e '.[dev]' to install in editable mode"
          '';
        };
      }
    ) // {
      inherit nixosModules;
    };
}
