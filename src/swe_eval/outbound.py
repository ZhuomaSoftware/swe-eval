"""DNS-pinned outbound HTTP. No redirects, environment proxies or URL secrets."""
import concurrent.futures,http.client,ipaddress,json,os,socket,ssl,time,threading
from urllib.parse import urlsplit
from .providers import ProviderError
_RESOLVER=concurrent.futures.ThreadPoolExecutor(max_workers=4,thread_name_prefix='provider-dns')
class OutboundDenied(ProviderError):pass

def normalize_url(value):
    try:
        u=urlsplit(value)
        if u.scheme not in ('https','http') or not u.hostname or u.username or u.password or u.query or u.fragment:raise ValueError()
        host=u.hostname.encode('idna').decode().lower();port=u.port or (443 if u.scheme=='https' else 80)
        if not 1<=port<=65535 or any(c.isspace() or ord(c)<32 for c in value) or '\\' in value:raise ValueError()
        bracket='['+host+']' if ':' in host else host
        origin=u.scheme+'://'+bracket+((':'+str(port)) if port!=(443 if u.scheme=='https' else 80) else '')
        return origin+(u.path.rstrip('/') or ''),origin,host,port
    except (ValueError,UnicodeError):raise OutboundDenied('invalid provider URL; use HTTP(S) without credentials, query or fragment') from None

def approved_origins():
    result=set()
    for value in os.getenv('SWE_APPROVED_PROVIDER_ORIGINS','').split(','):
        if value.strip():
            normalized,origin,_,_=normalize_url(value.strip())
            if normalized!=origin:raise OutboundDenied('approved provider origins must not contain a path')
            result.add(origin)
    return result

def validate_url(value):
    normalized,origin,host,port=normalize_url(value)
    if origin.startswith('http://') and origin not in approved_origins():raise OutboundDenied('HTTP requires an explicitly approved server-side provider origin')
    return normalized

def resolve_target(value,timeout):
    normalized,origin,host,port=normalize_url(validate_url(value));approved=origin in approved_origins()
    future=_RESOLVER.submit(socket.getaddrinfo,host,port,type=socket.SOCK_STREAM)
    try:records=future.result(timeout=max(.01,min(timeout,3)))
    except (OSError,concurrent.futures.TimeoutError):
        future.cancel();raise OutboundDenied('provider DNS unavailable or timed out') from None
    addresses=list(dict.fromkeys(row[4][0] for row in records))
    if not addresses:raise OutboundDenied('provider DNS has no usable address')
    for value in addresses:
        try:ip=ipaddress.ip_address(value)
        except ValueError:raise OutboundDenied('provider DNS returned an invalid address') from None
        if isinstance(ip,ipaddress.IPv6Address):
            if ip.ipv4_mapped:ip=ip.ipv4_mapped
            if isinstance(ip,ipaddress.IPv6Address) and (ip.sixtofour or ip.teredo):raise OutboundDenied('IPv6 transition addresses are forbidden')
        if str(ip) in ('100.100.100.200','168.63.129.16','fd00:ec2::254'):raise OutboundDenied('cloud metadata service address is forbidden')
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified or (not ip.is_global and not approved):raise OutboundDenied('provider address is not approved')
        # Never authorize cloud metadata/link-local through a private-origin exception.
        if ip in ipaddress.ip_network('169.254.0.0/16') or ip in ipaddress.ip_network('fe80::/10'):raise OutboundDenied('metadata/link-local provider addresses are forbidden')
    return normalized,host,port,addresses

class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self,host,port,address,timeout):super().__init__(host,port,timeout=timeout);self.address=address
    def connect(self):
        self.sock=socket.create_connection((self.address,self.port),timeout=self.timeout);self._request_socket=self.sock
class PinnedHTTPS(PinnedHTTP):
    def connect(self):
        super().connect();self.sock=ssl.create_default_context().wrap_socket(self.sock,server_hostname=self.host);self._request_socket=self.sock

def request_json(url,key,body=None,timeout=5):
    started=time.monotonic();url,host,port,addresses=resolve_target(url,timeout);remaining=timeout-(time.monotonic()-started)
    if remaining<=0:raise ProviderError('provider request timed out')
    u=urlsplit(url);connection=(PinnedHTTPS if u.scheme=='https' else PinnedHTTP)(host,port,addresses[0],remaining)
    headers={'Accept':'application/json','Content-Type':'application/json'}
    if key:headers['Authorization']='Bearer '+key
    response=None
    def abort():
        active=getattr(connection,"_request_socket",None)
        if active:
            try:active.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        connection.close()
    deadline=threading.Timer(remaining,abort);deadline.daemon=True;deadline.start()
    try:
        connection.request('POST' if body is not None else 'GET',u.path or '/',body=json.dumps(body).encode() if body is not None else None,headers=headers)
        response=connection.getresponse()
        if not 200<=response.status<300:raise ProviderError('upstream HTTP '+str(response.status))
        data=bytearray();maximum=2*1024*1024 if body is not None else 65536
        while True:
            remaining=timeout-(time.monotonic()-started)
            if remaining<=0:raise ProviderError('provider request timed out')
            connection.sock.settimeout(remaining) if connection.sock else None
            chunk=response.read1(min(65536,maximum+1-len(data)))
            if not chunk:break
            data.extend(chunk)
            if len(data)>maximum:raise ProviderError('upstream response exceeds bounded size')
        result=json.loads(data)
        if not isinstance(result,dict):raise ValueError()
        return result
    except ProviderError:raise
    except (OSError,ValueError,http.client.HTTPException):raise ProviderError('provider connection failed, timed out or returned invalid JSON') from None
    finally:
        deadline.cancel()
        if response is not None:response.close()
        connection.close()
