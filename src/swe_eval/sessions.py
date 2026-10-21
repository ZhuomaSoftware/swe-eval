"""Independent administrator sessions: no browser-held API bearer token."""
import hashlib
import hmac
import secrets
import time

COOKIE = 'swe_session'


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return f'pbkdf2_sha256$600000${salt}$' + hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()


def verify_password(password, configured):
    try:
        algorithm, rounds, salt, expected = configured.split('$')
        if algorithm != 'pbkdf2_sha256' or rounds != '600000' or len(salt)>128:
            return False
        actual = password_hash(password,salt).split('$')[-1]
        return hmac.compare_digest(expected,actual)
    except ValueError:
        return False


def hashed(value):
    return hashlib.sha256(value.encode()).hexdigest()


def issue(repo):
    token, csrf, expires = secrets.token_urlsafe(32), secrets.token_urlsafe(32), time.time()+8*3600
    with repo.connect(write=True) as db:
        db.execute('DELETE FROM admin_sessions WHERE expires_at<=?',(time.time(),))
        db.execute('INSERT INTO admin_sessions VALUES (?,?,?)',(hashed(token),hashed(csrf),expires))
    return token, csrf, expires


def authorized(repo, token, csrf=None):
    if not token or len(token)>200:
        return False
    with repo.connect() as db:
        row = db.execute('SELECT csrf_hash FROM admin_sessions WHERE token_hash=? AND expires_at>?',(hashed(token),time.time())).fetchone()
    return bool(row and (csrf is None or hmac.compare_digest(row[0],hashed(csrf))))
