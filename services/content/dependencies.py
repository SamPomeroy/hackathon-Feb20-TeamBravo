from fastapi import Header
from exceptions import AuthException

def require_user_id(x_user_id: str = Header(None)) -> str:
    if not x_user_id:
        raise AuthException()
    return x_user_id
