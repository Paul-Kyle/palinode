# NixOS module for the Palinode MCP HTTP server.
#
# Mirrors deploy/systemd/palinode-mcp.service.template.
# This module depends on services.palinode (palinode-service.nix) and will
# automatically enable the main palinode service when enabled.
#
# Usage:
#
#   {
#     inputs.palinode.url = "github:phasespace-labs/palinode";
#     outputs = { palinode, ... }: {
#       nixosConfigurations.your-host = nixpkgs.lib.nixosSystem {
#         modules = [
#           palinode.nixosModules.palinode
#           palinode.nixosModules.palinode-mcp
#           ({ ... }: {
#             services.palinode.enable = true;
#             services.palinode.dataDir = "/var/lib/palinode";
#             services.palinode-mcp.enable = true;
#           })
#         ];
#       };
#     };
#   }

{ config, lib, pkgs, ... }:

let
  cfg = config.services.palinode-mcp;
  # Inherit the main palinode config for shared options (user, group, dataDir, apiPort, package).
  palinodeCfg = config.services.palinode;
in
{
  # Import the main palinode module so services.palinode options are available.
  imports = [ ./palinode-service.nix ];

  options.services.palinode-mcp = {
    enable = lib.mkEnableOption "Palinode MCP HTTP server";

    port = lib.mkOption {
      type = lib.types.port;
      default = 6341;
      description = ''
        Port for the palinode MCP HTTP server (streamable-HTTP transport at /mcp/).
        Configure MCP clients with type "http" and url "http://host:<port>/mcp/".
      '';
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Whether to open the MCP port in the NixOS firewall.";
    };
  };

  config = lib.mkIf cfg.enable {
    # Enabling the MCP server implies the main palinode service must also be enabled.
    services.palinode.enable = lib.mkDefault true;

    # Palinode MCP service (mirrors palinode-mcp.service.template)
    systemd.services.palinode-mcp = {
      description = "Palinode MCP Server (streamable-HTTP transport)";
      documentation = [ "https://github.com/phasespace-labs/palinode" ];
      after = [ "network.target" "palinode-api.service" ];
      wants = [ "palinode-api.service" ];
      wantedBy = [ "multi-user.target" ];

      environment = {
        PALINODE_DIR = palinodeCfg.dataDir;
        PALINODE_API_HOST = "127.0.0.1";
        PALINODE_API_PORT = toString palinodeCfg.apiPort;
      };

      serviceConfig = {
        Type = "simple";
        User = palinodeCfg.user;
        Group = palinodeCfg.group;
        WorkingDirectory = palinodeCfg.dataDir;
        # palinode-mcp-sse is the historical alias for the streamable-HTTP entry point.
        # See pyproject.toml: palinode-mcp-sse = "palinode.mcp:main_sse"
        ExecStart = "${palinodeCfg.package}/bin/palinode-mcp-sse --port ${toString cfg.port}";
        Restart = "always";
        RestartSec = "5s";
        StandardOutput = "journal";
        StandardError = "journal";
        SyslogIdentifier = "palinode-mcp";

        # Security hardening
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ palinodeCfg.dataDir ];
        PrivateTmp = true;
      };
    };

    # Optionally open the MCP port in the firewall
    networking.firewall.allowedTCPPorts = lib.mkIf cfg.openFirewall [ cfg.port ];
  };
}
