"""
rvc_decoder
===========

Library for loading RV‑C specs & mappings and decoding CAN payloads.
"""

from .decode import get_bits, decode_payload, load_config_data

__all__ = [
    "get_bits",
    "decode_payload",
    "load_config_data",
]
