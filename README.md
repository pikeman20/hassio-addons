# Home Assistant Add-on Repository: Real-time Microphone Filter

This repository contains Home Assistant add-ons for advanced audio processing and microphone filtering.

## Add-ons

This repository contains the following add-ons:

### [Nginx Proxy Manager](./addon-nginx-proxy-manager)
Manage Nginx proxy hosts with a simple, powerful interface. Easily forward incoming connections, including free SSL, to Home Assistant, add-ons, or other services.

### [Assist Microphone Custom](./assist_microphone)
Home Assistant add-on that uses a local USB microphone or Pulse Server via TCP to control Assist. Part of the Year of Voice project.

### [Passive BLE Monitor](./ble_monitor)
Custom component for Home Assistant that passively monitors many different BLE devices of several brands. Can also be used as a device tracker for BLE devices.

### [Bumper](./bumper-dev)
Self-hosted central server for Ecovacs vacuum robots. Replaces the Ecovacs cloud, giving you full local control through a privacy-first, high-performance stack.

### [Ecovacs Bumper Addon](./ecovacs-bumper)
Runs the bumper-dev server as a Home Assistant addon, exposing multiple ports and supporting Nginx integration for full functionality.

## Installation

Add this repository to your Home Assistant instance:

1. Navigate to **Settings** → **Add-ons** → **Add-on Store**
2. Click on the **⋮** menu in the top right corner
3. Select **Repositories**
4. Add this repository URL: `https://github.com/pikeman20/hassio-addons`
5. Close the dialog
6. Click on it and press **Install**

## Support

For issues and feature requests, please:

1. Check the individual add-on documentation
2. Review the add-on logs for error messages
3. Create an issue in this repository with:
   - Home Assistant version
   - Add-on configuration
   - Relevant log messages
   - Audio device information

## License

This repository and its add-ons are released under the Apache License 2.0.