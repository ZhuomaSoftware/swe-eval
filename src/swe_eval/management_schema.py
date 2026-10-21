"""Strict administrative inputs. Credentials never enter ordinary payload JSON."""
from typing import Literal
from pydantic import Field,SecretStr,model_validator
from .schema import StrictModel,Capabilities,Pricing
ID=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$'
class ProviderWrite(StrictModel):
    id:str=Field(pattern=ID)
    display_name:str=Field(min_length=1,max_length=100)
    base_url:str=Field(min_length=8,max_length=1000)
    protocol:Literal['openai_compatible']='openai_compatible'
    request_timeout:float=Field(default=60,gt=0,le=600)
    enabled:bool=True
    archived:bool=False
    allow_no_api_key:bool=False
    api_key:SecretStr|None=Field(default=None,exclude=True)
    expected_revision:int|None=Field(default=None,ge=1)
class RevisionAction(StrictModel):
    expected_revision:int=Field(ge=1)
    enabled:bool|None=None
class SecretRotation(StrictModel):
    expected_revision:int=Field(ge=1)
    api_key:SecretStr
class CredentialRevoke(StrictModel):
    credential_version:int=Field(ge=1)
class ManagedModelWrite(StrictModel):
    id:str=Field(pattern=ID)
    display_name:str=Field(min_length=1,max_length=100)
    provider_id:str=Field(pattern=ID)
    model_id:str=Field(min_length=1,max_length=200)
    upstream_id:str=Field(pattern=ID)
    enabled:bool=True
    archived:bool=False
    data_origin:Literal['live','local_stub','unverified']='unverified'
    reasoning_effort:str|None=Field(default=None,min_length=1,max_length=30)
    capabilities:Capabilities=Field(default_factory=Capabilities)
    request_timeout:float=Field(default=60,gt=0,le=600)
    max_output_tokens:int=Field(default=2048,ge=1,le=100000)
    max_total_tokens:int|None=Field(default=30000,ge=1,le=1000000)
    max_agent_steps:int=Field(default=12,ge=1,le=1000)
    max_model_calls:int=Field(default=15,ge=1,le=1000)
    max_evaluation_duration:int=Field(default=300,ge=1,le=3600)
    max_context_chars:int=Field(default=160000,ge=1000,le=2000000)
    pricing:Pricing|None=None
    expected_revision:int|None=Field(default=None,ge=1)
    @model_validator(mode='after')
    def bounds(self):
        if self.max_total_tokens and self.max_output_tokens>self.max_total_tokens:raise ValueError('output limit must not exceed total token budget')
        if self.reasoning_effort and not self.capabilities.reasoning_effort:raise ValueError('reasoning capability is not enabled')
        return self
class SubsetWrite(StrictModel):
    id:str=Field(pattern=ID)
    name:str=Field(min_length=1,max_length=120)
    task_ids:list[str]=Field(min_length=1,max_length=100)
    expected_revision:int|None=Field(default=None,ge=1)
    @model_validator(mode='after')
    def unique(self):
        if len(self.task_ids)!=len(set(self.task_ids)):raise ValueError('subset task IDs must be unique')
        return self
class AdministrationJob(StrictModel):
    kind:Literal['dataset_import','environment_validation']
    dataset:Literal['swebench-verified']='swebench-verified'
    revision:str=Field(pattern=r'^[a-f0-9]{40}$')
    instance_ids:list[str]=Field(default_factory=list,max_length=5)
    prepare:bool=False
    timeout:int=Field(default=300,ge=1,le=600)
    wall_timeout:int=Field(default=1800,ge=1,le=3600)
    idempotency_key:str=Field(min_length=8,max_length=100,pattern=r'^[a-zA-Z0-9_.-]+$')
    @model_validator(mode='after')
    def bounded(self):
        if self.kind=='environment_validation' and not self.instance_ids:raise ValueError('explicit validation instance IDs required')
        if self.kind=='dataset_import' and (self.prepare or self.instance_ids):raise ValueError('metadata imports never prepare environments')
        if len(self.instance_ids)!=len(set(self.instance_ids)):raise ValueError('duplicate validation instances')
        return self
