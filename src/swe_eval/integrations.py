"""Read-only sub2api adapter for source-inspected effective-models GET contract.

No account-list or credential endpoint is ever called. Mappings are server-owned.
"""
import json
import os
import urllib.request
import urllib.error
from urllib.parse import urlsplit
from pydantic import Field
from .schema import StrictModel


class Mapping(StrictModel):
    profile_id: str
    group_id: int = Field(gt=0, le=2**63-1)
    upstream_source_id: str | None = None
    fixed_upstream_verified: bool = False


class IntegrationConfig(StrictModel):
    source_id: str = Field(pattern=r'^[a-zA-Z0-9_.-]{1,80}$')
    base_url: str
    admin_key_env: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]*$')
    mappings: list[Mapping] = Field(max_length=100)
    allow_http: bool = False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def synchronize(path, profiles):
    try:
        config=IntegrationConfig.model_validate_json(path.read_text())
        url=urlsplit(config.base_url)
        if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError()
        if url.scheme!='https' and not config.allow_http:
            raise ValueError()
        if any(m.profile_id not in profiles or m.fixed_upstream_verified for m in config.mappings):
            # Metadata discovery cannot attest a gateway's concrete routing path.
            raise ValueError()
        key=os.environ.get(config.admin_key_env,'')
        if not key or '\n' in key or '\r' in key:
            raise ValueError()
    except (OSError,ValueError):
        raise ValueError('SWE_INTEGRATION_FILE: invalid metadata mapping or unavailable server-side admin key') from None
    items=[]; cache={}
    for mapping in config.mappings:
        if mapping.group_id not in cache:
            target=config.base_url.rstrip('/')+f'/api/v1/admin/groups/{mapping.group_id}/effective-models'
            request=urllib.request.Request(target,headers={'x-api-key':key,'Accept':'application/json'},method='GET')
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect).open(request,timeout=15) as response:
                    raw=response.read(1048577)
                if len(raw)>1048576:
                    raise ValueError()
                body=json.loads(raw)
                if not isinstance(body,dict) or body.get('code')!=0 or not isinstance(body.get('data'),dict):
                    raise ValueError()
                models=body['data'].get('models')
                if not isinstance(models,list) or len(models)>10000 or any(not isinstance(x,str) or len(x)>200 for x in models):
                    raise ValueError()
                cache[mapping.group_id]=set(models)
            except (OSError,ValueError,urllib.error.HTTPError):
                raise ValueError('sub2api metadata unavailable or unsupported effective-models schema; no changes imported') from None
        profile=profiles[mapping.profile_id]
        items.append(dict(profile_id=profile.id,model_id=profile.model_id,
            source_identity=f'{config.source_id}:group:{mapping.group_id}',
            upstream_source_id=mapping.upstream_source_id,upstream_verified=False,
            available=profile.model_id in cache[mapping.group_id],pricing=None,
            inference_capabilities='not_exposed'))
    return config.source_id,{'schema_version':'sub2api-metadata-v1','items':items,'read_only':True}
