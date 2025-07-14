# Ecovacs Bumper Home Assistant Addon

This addon runs the [bumper-dev](https://github.com/pikeman20/bumper-dev) server as a Home Assistant addon.

## Features

- Runs bumper-dev from local source
- Installs dependencies using uv
- Exposes port 8080

## Usage

1. Place your local bumper-dev source in `../bumper-dev` relative to this addon.
2. Build and start the addon from Home Assistant Supervisor.

No configuration options are required by default.