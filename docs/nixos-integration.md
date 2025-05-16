# Using rvc2api in NixOS Configurations

This document explains how to include and configure rvc2api in other NixOS systems and flakes.

## Overview

rvc2api is packaged as a Nix flake with:

- A standalone Python package
- A NixOS module for system integration
- Configuration options for customization

## Basic Usage

### Including rvc2api in Your Flake

Add rvc2api to your flake inputs:

```nix
{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

    # Add rvc2api as a dependency
    rvc2api.url = "github:carpenike/rvc2api";
    rvc2api.inputs.nixpkgs.follows = "nixpkgs"; # Optional: Use your nixpkgs
  };

  outputs = { self, nixpkgs, rvc2api, ... }: {
    # Your outputs...
  };
}
```

### As a Package

To simply include rvc2api as a package:

```nix
environment.systemPackages = [
  inputs.rvc2api.packages.${system}.rvc2api
];
```

### As a NixOS Module

For a complete integration with configuration options:

```nix
{
  imports = [
    inputs.rvc2api.nixosModules.rvc2api
  ];

  rvc2api = {
    enable = true;
    settings = {
      # See detailed configuration options in docs/nixos-module.md
      canbus.channels = [ "can0" ];
    };
  };
}
```

For complete configuration options, see the [NixOS Module Documentation](nixos-module.md).
];

# Enable the service

rvc2api.enable = true;

# Configure options

rvc2api.settings = {
pushover = {
enable = true;
apiToken = "your-pushover-api-token";
userKey = "your-pushover-user-key";
};
};
}

````

## Configuration Options

rvc2api provides the following configuration options:

### Basic Options

```nix
rvc2api = {
  enable = true;        # Enable the rvc2api module
  package = pkgs.rvc2api;  # Optional: override the package
};
````

### Pushover Notifications

```nix
rvc2api.settings.pushover = {
  enable = true;        # Enable Pushover integration
  apiToken = "token";   # Your Pushover API token
  userKey = "key";      # Your Pushover user key
};
```

## Development Usage

To develop against rvc2api:

```bash
# Enter the development shell
nix develop github:carpenike/rvc2api

# Or specify a specific attribute
nix develop github:carpenike/rvc2api#ci  # For CI environment
```

## Architecture Support

rvc2api supports the following architectures:

- x86_64-linux
- aarch64-linux (Raspberry Pi 4, etc.)

## Version Management

rvc2api follows semantic versioning with releases managed via GitHub's release-please automation.
You can pin to specific tags in your flake for stability:

```nix
rvc2api.url = "github:carpenike/rvc2api/v1.0.0";
```
