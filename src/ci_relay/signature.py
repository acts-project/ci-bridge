import hmac
from typing import Union


class Signature:
    def __init__(self, secret: str):
        self.secret = secret

    def create(self, payload: Union[str, bytes]) -> str:
        """Create a signature for the given payload."""
        if isinstance(payload, str):
            payload = payload.encode()
        return hmac.new(
            self.secret,
            payload,
            digestmod="sha512",
        ).hexdigest()

    def verify(self, payload: Union[str, bytes], signature: str) -> bool:
        """Verify that the signature matches the payload."""
        if isinstance(payload, str):
            payload = payload.encode()
        expected_signature = hmac.new(
            self.secret,
            payload,
            digestmod="sha512",
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)
