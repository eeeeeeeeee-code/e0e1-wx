# -*- coding: utf-8 -*-

import hashlib
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2


def hmac_sha1(key, msg):
    block_size = 64
    if len(key) > block_size:
        key = hashlib.sha1(key).digest()
    key = key + b'\x00' * (block_size - len(key))
    o_key_pad = bytes(x ^ 0x5c for x in key)
    i_key_pad = bytes(x ^ 0x36 for x in key)
    return hashlib.sha1(o_key_pad + hashlib.sha1(i_key_pad + msg).digest()).digest()


def generate_aes_key(wxid, salt, iv):
    dk = PBKDF2(wxid.encode(), salt.encode(), dkLen=32, count=1000, prf=lambda p, s: hmac_sha1(p, s))
    cipher = AES.new(dk, AES.MODE_CBC, iv.encode())
    return dk, cipher
