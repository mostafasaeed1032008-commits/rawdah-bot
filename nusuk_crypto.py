# -*- coding: utf-8 -*-
"""
nusuk_crypto.py
===============
Cryptographic utilities reverse-engineered from official Nusuk portal bundle (module 4152).
Handles AES-128-CBC encryption/decryption, dynamic key extraction, and request token signing.
"""

import base64
import json
import random
import string
import time
from typing import Dict, Any, Optional
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


def decrypt_with_key(key_str: str, ciphertext_b64: str) -> str:
    """Decrypts base64 AES-CBC ciphertext using the supplied 16-character UTF-8 key."""
    key_bytes = key_str.encode("utf-8")
    iv_bytes = key_bytes  # In Nusuk Webpack bundle: { iv: M } where M is key
    ct_bytes = base64.b64decode(ciphertext_b64)
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    pt_padded = cipher.decrypt(ct_bytes)
    pt = unpad(pt_padded, AES.block_size)
    return pt.decode("utf-8")


def encrypt_with_key(key_str: str, plaintext: str) -> str:
    """Encrypts plaintext with AES-128-CBC using key as IV, returning base64 string."""
    key_bytes = key_str.encode("utf-8")
    iv_bytes = key_bytes
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    padded = pad(plaintext.encode("utf-8"), AES.block_size)
    ct = cipher.encrypt(padded)
    return base64.b64encode(ct).decode("utf-8")


def append_key_for_encrypted_data(key_str: str, ct_b64: str) -> str:
    """
    Nusuk key packing format:
    first 4 characters of key + base64 ciphertext + remaining 12 characters of key.
    """
    return key_str[:4] + ct_b64 + key_str[4:]


def get_object_from_string(encrypted_str: str) -> Optional[Dict[str, Any]]:
    """
    Unpacks and decrypts response.data from Nusuk API.
    Extracts embedded 16-char key (chars 0..4 + last 12 chars), decrypts payload,
    and returns parsed JSON dictionary.
    """
    if not encrypted_str or len(encrypted_str) <= 16:
        return None
    try:
        key_str = encrypted_str[:4] + encrypted_str[-12:]
        ct_b64 = encrypted_str[4:-12]
        decrypted_json_str = decrypt_with_key(key_str, ct_b64)
        return json.loads(decrypted_json_str)
    except Exception as e:
        return None


def generate_random_string(length: int = 16) -> str:
    """Generates an alphanumeric random string matching Nusuk randomString helper."""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def generate_bearer_token(auth_token: str, target_url: str) -> str:
    """
    Generates the dynamic Authorization Bearer token expected by Nusuk interceptor:
    { "token": auth_token, "timestamp": now_ms, "targetUrl": target_url }
    encrypted with a fresh random 16-char key and packed via append_key_for_encrypted_data.
    """
    now_ms = int(time.time() * 1000)
    payload = {
        "token": auth_token,
        "timestamp": now_ms,
        "targetUrl": target_url
    }
    key_16 = generate_random_string(16)
    plaintext = json.dumps(payload, separators=(',', ':'))
    encrypted_ct = encrypt_with_key(key_16, plaintext)
    return append_key_for_encrypted_data(key_16, encrypted_ct)
