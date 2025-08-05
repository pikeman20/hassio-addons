# Ecovacs Bumper Home Assistant Addon

This addon runs the [bumper-dev](https://github.com/pikeman20/bumper-dev) server as a Home Assistant addon.

## Features

- Runs bumper-dev from local source
- Installs dependencies using uv
- Exposes port 8007, 1883, 8883, 1223, 5223

## Usage

1. Build and start the addon from Home Assistant Supervisor.

No configuration options are required by default.

**Note:**  
When setting up the integration, the `override_mqtt_url` and `override_rest_url` fields should be set using the IP address of the bumper addon container.  
For example:  
```json
"override_mqtt_url": "mqtts://172.30.33.0:8883",
"override_rest_url": "http://172.30.33.0:8007"
```
Here, `172.30.33.0` is the IP address of the bumper addon container. Adjust this IP as needed for your environment.

## Nginx Integration

To enable full functionality, you must include the content of nginx.conf
in your Home Assistant addon nginx configuration. This configuration sets up stream proxying and port routing for bumper-dev services.

Example /addon_configs/047b89f3_nginxproxymanager/nginx/custom/stream.conf content:
```
    resolver 127.0.0.11 ipv6=off;  # Docker DNS resolver
    # map_hash_bucket_size 64;

    ########################################################
    # Logging: Define a custom log format to record key variables.
    ########################################################
    log_format upstreaminfo '$remote_addr [$time_local] '
        'ADDR:"$proxy_protocol_addr", '
        'SNI:"$ssl_preread_server_name", '
        'ALPN:"$ssl_preread_alpn_protocols", '
        'final_port:$final_port';

    # Write logs to addon log.
    access_log /proc/1/fd/1 upstreaminfo;

    ########################################################
    # Choose the final port.
    ########################################################
    map $ssl_preread_server_name $final_port {
        ~^.*(mq).*\.eco(vacs|user)\.(net|com)$    8883; # MQTTS
        ~^.*(mq).*\.aliyuncs\.(com)$              8883; # MQTTS
        # ~^.*(mq).*\.aliyuncs\.(com)$              1883; # MQTTS
        ~^.*eco(vacs|user)\.(net|com)$             443; # HTTPS
        ~^.*aliyuncs\.com$                         443; # HTTPS
        ~^.*aliyun\.com$                           443; # HTTPS -> MQTTS
		""                                        8883; # Connect by IP
        default                                   1234; # Fallback to NPM Manager
    }
    map $final_port $proxy_target {
        1234   127.0.0.1:443;
        default addon_047b89f3_ecovacs-bumper:$final_port;
    }

    server {
        listen 1443;
        ssl_preread on;
        proxy_pass $proxy_target;
    }
    server {
        listen 8007;
        proxy_pass addon_047b89f3_ecovacs-bumper:8007;
    }

    server {
        listen 1883;
        proxy_pass addon_047b89f3_ecovacs-bumper:1883;
    }

    server {
        listen 8883;
        proxy_pass addon_047b89f3_ecovacs-bumper:8883;
    }

    server {
        listen 5223;
        proxy_pass addon_047b89f3_ecovacs-bumper:5223;
    }
```