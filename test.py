import base64
import hashlib
import hmac
import struct
import time
from datetime import datetime, timezone

DEST_TYPES = {
    0: "home",
    1: "feedback",
    2: "submit",
    3: "later",
    4: "gallery",
}

token = "AIAG-W3MQ-QQCO-DBAV-QPRJ-HHMR-TB3F-IMQQ-AB2U-3U6Z-E7C6-4FYR-BOZB-6"
secret = "secretisasecret"

# 1. Decode Base32
encoded = token.replace("-", "").upper()
raw = base64.b32decode(encoded + "=" * ((8 - len(encoded) % 8) % 8))

# 2. Extract fixed fields
version = raw[0]
dest_type_byte = raw[1]
expiry = struct.unpack(">I", raw[2:6])[0]
nonce = raw[6:14]
phone_bytes = raw[14:20]
dest_id_length = raw[20]

# 3. Extract variable destination ID and signature
dest_id_start = 21
dest_id_end = dest_id_start + dest_id_length

dest_id = raw[dest_id_start:dest_id_end].decode("utf-8")
body = raw[:dest_id_end]
provided_tag = raw[dest_id_end:]

# 4. Decode packed phone digits
phone = "".join(
    f"{byte >> 4}{byte & 0x0F}"
    for byte in phone_bytes
).lstrip("0")

# 5. Verify HMAC
expected_tag = hmac.new(
    secret.encode(),
    body,
    hashlib.sha256
).digest()[:12]

signature_valid = hmac.compare_digest(
    provided_tag,
    expected_tag
)

# 6. Print results
print("Version:", version)
print("Destination:", DEST_TYPES.get(dest_type_byte, "UNKNOWN"))
print("Phone:", phone)
print("Destination ID:", dest_id or None)
print("Nonce:", nonce.hex())
print("Expiry:", datetime.fromtimestamp(expiry, timezone.utc))
print("Expired:", time.time() > expiry)
print("Signature valid:", signature_valid)

if version != 2:
    print("WARNING: Unexpected token version")

if len(provided_tag) != 12:
    print("WARNING: Unexpected signature length")
