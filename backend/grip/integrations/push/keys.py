"""Make a key pair for web push::

    python -m grip.integrations.push.keys

Prints the private key for ``PUSH_VAPID_PRIVATE_KEY`` and, for reference,
the public key browsers will be given. The private key is a secret of the
instance. Changing it ends every subscription: browsers subscribe for one
key and devices must subscribe again.
"""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric import ec

from grip.integrations.push.config import b64url, public_point


def generate() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private = b64url(key.private_numbers().private_value.to_bytes(32, "big"))
    return private, b64url(public_point(key))


def main() -> None:
    private, public = generate()
    print(f"PUSH_VAPID_PRIVATE_KEY={private}")
    print(f"# public key (derived, not a setting): {public}")


if __name__ == "__main__":
    main()
