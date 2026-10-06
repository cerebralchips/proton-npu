#!/usr/bin/env python3
"""Small ELF64 memory images for 64-bit loader address/bounds tests."""
import struct

PRELOAD = [(0x100008000, 0x0123456789abcdef), (0x1fffffff8, 0xfedcba9876543210)]

def image(segments):
    """segments: (physical address, payload bytes, in-memory size)."""
    offset = 64 + 56*len(segments)
    header = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01\x01'+bytes(9),
                         2, 243, 1, 0, 64, 0, 0, 64, 56, len(segments), 0, 0, 0)
    headers, payload = [], []
    for address, data, size in segments:
        headers.append(struct.pack('<IIQQQQQQ', 1, 6, offset, address, address, len(data), size, 8))
        payload.append(data)
        offset += len(data)
    return header + b''.join(headers) + b''.join(payload)
