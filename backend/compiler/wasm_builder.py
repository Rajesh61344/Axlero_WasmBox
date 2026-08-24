"""
WasmBox WASM Module Builder.

Low-level pure Python WebAssembly binary builder. Constructs valid WASM
modules programmatically without external dependencies.
"""

from __future__ import annotations

import json
from typing import Any

WASM_MAGIC = b'\x00asm'
WASM_VERSION = b'\x01\x00\x00\x00'

# Section IDs
CUSTOM = 0
TYPE = 1
IMPORT = 2
FUNCTION = 3
TABLE = 4
MEMORY = 5
GLOBAL = 6
EXPORT = 7
START = 8
ELEMENT = 9
CODE = 10
DATA = 11

# Value Types
I32 = 0x7F
I64 = 0x7E
F32 = 0x7D
F64 = 0x7C
FUNCREF = 0x70

# Export Kinds
FUNC = 0x00
TABLE = 0x01
MEM = 0x02
GLOBAL = 0x03


def encode_unsigned_leb128(value: int) -> bytes:
    """Encode an unsigned integer into LEB128 format."""
    if value < 0:
        raise ValueError("Value must be non-negative")
    if value == 0:
        return b'\x00'
    result = bytearray()
    while value > 0:
        byte = value & 0x7F
        value >>= 7
        if value != 0:
            byte |= 0x80
        result.append(byte)
    return bytes(result)


def encode_signed_leb128(value: int) -> bytes:
    """Encode a signed integer into LEB128 format."""
    result = bytearray()
    more = True
    while more:
        byte = value & 0x7F
        value >>= 7
        if (value == 0 and (byte & 0x40) == 0) or (value == -1 and (byte & 0x40) != 0):
            more = False
        else:
            byte |= 0x80
        result.append(byte)
    return bytes(result)


def decode_unsigned_leb128(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode an unsigned LEB128 integer from data starting at offset.
    Returns (value, next_offset).
    """
    result = 0
    shift = 0
    while True:
        if offset >= len(data):
            raise ValueError("Unexpected end of LEB128 data")
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return result, offset


class WasmModuleBuilder:
    """Constructs valid WebAssembly modules programmatically."""

    @staticmethod
    def _build_section(section_id: int, payload: bytes) -> bytes:
        """Build a single WASM section."""
        return bytes([section_id]) + encode_unsigned_leb128(len(payload)) + payload

    @staticmethod
    def _build_custom_section(name: str, data: bytes) -> bytes:
        """Build a custom section with a given name and payload data."""
        name_bytes = name.encode("utf-8")
        payload = encode_unsigned_leb128(len(name_bytes)) + name_bytes + data
        return WasmModuleBuilder._build_section(CUSTOM, payload)

    @staticmethod
    def _build_type_section(func_types: list[tuple[list[int], list[int]]]) -> bytes:
        """Build a type section.
        func_types is a list of (param_types, result_types).
        """
        payload = bytearray(encode_unsigned_leb128(len(func_types)))
        for params, results in func_types:
            payload.append(0x60)  # function form
            payload.extend(encode_unsigned_leb128(len(params)))
            for p in params:
                payload.append(p)
            payload.extend(encode_unsigned_leb128(len(results)))
            for r in results:
                payload.append(r)
        return WasmModuleBuilder._build_section(TYPE, bytes(payload))

    @staticmethod
    def _build_function_section(type_indices: list[int]) -> bytes:
        """Build a function section mapping functions to their type indices."""
        payload = bytearray(encode_unsigned_leb128(len(type_indices)))
        for type_idx in type_indices:
            payload.extend(encode_unsigned_leb128(type_idx))
        return WasmModuleBuilder._build_section(FUNCTION, bytes(payload))

    @staticmethod
    def _build_memory_section(min_pages: int, max_pages: int | None) -> bytes:
        """Build a memory section defining linear memory."""
        payload = bytearray(encode_unsigned_leb128(1))  # 1 memory
        if max_pages is not None:
            payload.append(0x01)  # flags: limits have max
            payload.extend(encode_unsigned_leb128(min_pages))
            payload.extend(encode_unsigned_leb128(max_pages))
        else:
            payload.append(0x00)  # flags: no max
            payload.extend(encode_unsigned_leb128(min_pages))
        return WasmModuleBuilder._build_section(MEMORY, bytes(payload))

    @staticmethod
    def _build_export_section(exports: list[tuple[str, int, int]]) -> bytes:
        """Build an export section.
        exports is a list of (name, kind, index).
        """
        payload = bytearray(encode_unsigned_leb128(len(exports)))
        for name, kind, index in exports:
            name_bytes = name.encode("utf-8")
            payload.extend(encode_unsigned_leb128(len(name_bytes)))
            payload.extend(name_bytes)
            payload.append(kind)
            payload.extend(encode_unsigned_leb128(index))
        return WasmModuleBuilder._build_section(EXPORT, bytes(payload))

    @staticmethod
    def _build_code_section(function_bodies: list[bytes]) -> bytes:
        """Build a code section containing function bodies."""
        payload = bytearray(encode_unsigned_leb128(len(function_bodies)))
        for body in function_bodies:
            payload.extend(encode_unsigned_leb128(len(body)))
            payload.extend(body)
        return WasmModuleBuilder._build_section(CODE, bytes(payload))

    @staticmethod
    def build_plugin_module(
        source: str,
        manifest_json: bytes,
        metadata_json: bytes,
        min_memory_pages: int = 1,
        max_memory_pages: int = 160
    ) -> bytes:
        """Build a complete valid WASM module with embedded plugin data."""
        module = bytearray(WASM_MAGIC + WASM_VERSION)

        # 1. Type section: () -> i32
        module.extend(WasmModuleBuilder._build_type_section([([], [I32])]))

        # 2. Function section: one function, type index 0
        module.extend(WasmModuleBuilder._build_function_section([0]))

        # 3. Memory section
        module.extend(WasmModuleBuilder._build_memory_section(min_memory_pages, max_memory_pages))

        # 4. Export section: _start (func 0), memory (mem 0)
        exports = [
            ("memory", MEM, 0),
            ("_start", FUNC, 0)
        ]
        module.extend(WasmModuleBuilder._build_export_section(exports))

        # 5. Code section: func body returns 0
        # local_count(leb128) + instructions + end
        # num_local_groups = 0
        # i32.const 0 = 0x41 0x00
        # end = 0x0B
        func_body = bytes([0x00, 0x41, 0x00, 0x0B])
        module.extend(WasmModuleBuilder._build_code_section([func_body]))

        # 6-8. Custom sections
        module.extend(WasmModuleBuilder._build_custom_section("wasmbox_source", source.encode("utf-8")))
        module.extend(WasmModuleBuilder._build_custom_section("wasmbox_manifest", manifest_json))
        module.extend(WasmModuleBuilder._build_custom_section("wasmbox_metadata", metadata_json))

        return bytes(module)


def is_valid_wasm_header(data: bytes) -> bool:
    """Check if the bytes start with the WASM magic number and version."""
    if len(data) < 8:
        return False
    return data[:4] == WASM_MAGIC and data[4:8] == WASM_VERSION


def extract_custom_section(wasm_bytes: bytes, section_name: str) -> bytes | None:
    """Extract a named custom section from a WASM binary."""
    if not is_valid_wasm_header(wasm_bytes):
        return None

    offset = 8
    target_name_bytes = section_name.encode("utf-8")
    
    while offset < len(wasm_bytes):
        section_id = wasm_bytes[offset]
        offset += 1
        section_size, offset = decode_unsigned_leb128(wasm_bytes, offset)
        
        if section_id == CUSTOM:
            name_len, name_offset = decode_unsigned_leb128(wasm_bytes, offset)
            name_bytes = wasm_bytes[name_offset:name_offset + name_len]
            if name_bytes == target_name_bytes:
                data_start = name_offset + name_len
                data_size = section_size - (data_start - offset)
                return wasm_bytes[data_start:data_start + data_size]
        
        offset += section_size
        
    return None


def list_custom_sections(wasm_bytes: bytes) -> list[str]:
    """Return names of all custom sections in a WASM binary."""
    if not is_valid_wasm_header(wasm_bytes):
        return []

    sections = []
    offset = 8
    
    while offset < len(wasm_bytes):
        section_id = wasm_bytes[offset]
        offset += 1
        section_size, offset = decode_unsigned_leb128(wasm_bytes, offset)
        
        if section_id == CUSTOM:
            name_len, name_offset = decode_unsigned_leb128(wasm_bytes, offset)
            name_bytes = wasm_bytes[name_offset:name_offset + name_len]
            try:
                sections.append(name_bytes.decode("utf-8"))
            except UnicodeDecodeError:
                pass
                
        offset += section_size
        
    return sections
