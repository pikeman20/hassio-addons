# Ecovacs Bumper Home Assistant Addon

This addon runs the [bumper-dev](https://github.com/pikeman20/bumper-dev) server as a Home Assistant addon.

## Features

- Runs bumper-dev from local source
- Installs dependencies using uv
- Exposes port 8007, 1883, 8883, 1223, 5223

## Usage

1. Place your local bumper-dev source in `../bumper-dev` relative to this addon.
2. Build and start the addon from Home Assistant Supervisor.

No configuration options are required by default.

## Nginx Integration

To enable full functionality, you must include the content of nginx.conf
in your Home Assistant addon nginx configuration. This configuration sets up stream proxying and port routing for bumper-dev services.

Example nginx.conf content:
```
# Global logging at debug level
error_log stderr;
# error_log stderr debug;
pid /var/run/nginx.pid;

events { }

stream {
    resolver 127.0.0.11 ipv6=off;  # Docker DNS resolver

    log_format upstreaminfo '$remote_addr [$time_local] '
        'ADDR:"$proxy_protocol_addr", '
        'SNI:"$ssl_preread_server_name", '
        'ALPN:"$ssl_preread_alpn_protocols", '
        'final_port:$final_port';

    access_log /dev/stdout upstreaminfo;

    map $ssl_preread_server_name $final_port {
        ~^.*(mq).*\.eco(vacs|user)\.(net|com)$    8883; # MQTTS
        ~^.*(mq).*\.aliyuncs\.(com)$              8883; # MQTTS
        # ~^.*(mq).*\.aliyuncs\.(com)$              1883; # MQTTS
        ~^.*eco(vacs|user)\.(net|com)$             443; # HTTPS
        ~^.*aliyuncs\.com$                         443; # HTTPS
        ~^.*aliyun\.com$                           443; # HTTPS
        default                                   8883; # MQTTS
    }

    server {
        listen 443;
        ssl_preread  on;
        proxy_pass bumper:$final_port;
    }

    server {
        listen 8007;
        proxy_pass bumper:8007;
    }

    server {
        listen 1883;
        proxy_pass bumper:1883;
    }

    server {
        listen 8883;
        proxy_pass bumper:8883;
    }

    server {
        listen 5223;
        proxy_pass bumper:5223;
    }
}
```