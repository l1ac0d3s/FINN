"""Create the keys for push notifications. Run once, on any machine with Python:

    python -m server.push_keys

It prints three lines to paste into Render's environment variables: VAPID_PUBLIC_KEY, VAPID_PRIVATE_B64
and VAPID_SUBJECT. Keep the private key secret. Do not commit it.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def make_keys():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    public_b64 = base64.urlsafe_b64encode(public).decode().rstrip("=")
    private_b64 = base64.b64encode(pem).decode()
    return public_b64, private_b64


if __name__ == "__main__":
    public_key, private_key = make_keys()
    print("VAPID_PUBLIC_KEY=" + public_key)
    print("VAPID_PRIVATE_B64=" + private_key)
    print("VAPID_SUBJECT=mailto:your-address@example.com")
