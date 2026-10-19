"""HTTPS transport for untrusted personal model endpoints, pinned to validated public IPs."""
import ipaddress
import socket

import httpx


class PublicTransport(httpx.HTTPTransport):
    def handle_request(self, request):
        url = request.url
        if url.scheme != 'https' or url.port not in (None, 443):
            raise ValueError('模型服务必须使用公开 HTTPS 地址。')
        addresses = socket.getaddrinfo(url.host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ValueError('模型服务不能访问内网或保留地址。')
        # Avoid a second hostname resolution between validation and connection.
        # Keep TLS certificate validation/SNI and HTTP Host bound to the original name.
        address = next((row[4][0] for row in addresses if row[0] == socket.AF_INET), addresses[0][4][0])
        headers = request.headers.copy()
        headers['Host'] = url.netloc.decode('ascii')
        pinned = httpx.Request(request.method, url.copy_with(host=address), headers=headers,
                               stream=request.stream, extensions={**request.extensions, 'sni_hostname': url.host})
        return super().handle_request(pinned)


def public_client(settings):
    if not settings.get('public_endpoint_only'):
        return {}
    return {'http_client': httpx.Client(transport=PublicTransport(), follow_redirects=False,
                                       trust_env=False, timeout=float(settings.get('timeout', 180)))}
