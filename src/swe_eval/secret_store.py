"""Authenticated encryption; master material is supplied by the operator only."""
import base64
import hashlib
import os
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


class SecretUnavailable(ValueError):
    pass


class SecretBox:
    def __init__(self):
        try:
            value=os.environ.get('SWE_CONFIG_MASTER_KEY','')
            key=base64.b64decode(value,altchars=b'-_',validate=True)
            if len(key)!=32:raise ValueError()
        except (ValueError,TypeError):
            raise SecretUnavailable('SWE_CONFIG_MASTER_KEY must be an externally supplied base64 32-byte key') from None
        self._cipher=AESGCM(key)
        self.key_id=hashlib.sha256(key).hexdigest()[:16]

    def seal(self,value,aad):
        if not isinstance(value,str) or not 1<=len(value)<=8192 or '\n' in value or '\r' in value:
            raise SecretUnavailable('invalid provider credential')
        nonce=secrets.token_bytes(12)
        return nonce+self._cipher.encrypt(nonce,value.encode(),aad.encode())

    def open(self,sealed,aad,key_id):
        if key_id!=self.key_id:raise SecretUnavailable('credential master key does not match')
        try:return self._cipher.decrypt(sealed[:12],sealed[12:],aad.encode()).decode()
        except (InvalidTag,ValueError,UnicodeError):
            raise SecretUnavailable('provider credential authentication failed') from None
