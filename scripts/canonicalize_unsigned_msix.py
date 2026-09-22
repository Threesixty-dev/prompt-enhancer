"""Fresh pre-sign copy changing only paired ZIP DOS timestamp fields."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_msix_candidate as pack
from prompt_enhancer.infrastructure.updates.msix_preflight import _resolve_zip64_extra

STAMP = struct.pack("<HH", 0, 33)  # 1980-01-01 00:00:00, DOS format.


def exact(stream, offset, count):
    if offset < 0 or count < 0 or count > 8 * 1024 * 1024:
        raise ValueError()
    stream.seek(offset)
    value = stream.read(count)
    if len(value) != count:
        raise ValueError()
    return value


def extras(value):
    """Only ZIP64 is supported: reject timestamp and unknown extensions."""
    position = 0
    seen = set()
    while position < len(value):
        if position + 4 > len(value):
            raise ValueError()
        tag, size = struct.unpack_from("<HH", value, position)
        if tag != 1 or tag in seen or position + 4 + size > len(value):
            raise ValueError()
        seen.add(tag)
        position += 4 + size


def patch_map(stream, size):
    if not pack._bounded_zip_central_directory(stream.fileno(), size=size):
        raise ValueError()
    tail = exact(stream, max(0, size - 65557), min(size, 65557))
    marker = tail.rfind(b"PK\x05\x06")
    end = struct.unpack_from("<4s4H2LH", tail, marker)
    end_offset = size - len(tail) + marker
    central_size, central_offset = end[5:7]
    if end_offset >= 20 and exact(stream, end_offset - 20, 4) == b"PK\x06\x07":
        locator = struct.unpack("<4sLQL", exact(stream, end_offset - 20, 20))
        z = struct.unpack("<4sQ2H2L4Q", exact(stream, locator[2], 56))
        central_size, central_offset = z[8:10]
    central = exact(stream, central_offset, central_size)
    position = 0
    records = []
    patches = []
    names = set()
    while position < len(central):
        fields = struct.unpack_from("<4s6H3L5H2L", central, position)
        name_length, extra_length, comment_length = fields[10:13]
        name = central[position + 46:position + 46 + name_length]
        extra = central[position + 46 + name_length:position + 46 + name_length + extra_length]
        extras(extra)
        if (not name or name.lower() in names or name.lower() == b"appxsignature.p7x"
                or fields[3] & (1 | 64 | 8192) or fields[4] not in (0, 8)):
            raise ValueError()
        names.add(name.lower())
        resolved = _resolve_zip64_extra(extra, fields[9], fields[8], fields[16], fields[13])
        if resolved is None:
            raise ValueError()
        unpacked, compressed, local_offset, disk = resolved
        local = struct.unpack("<4s5H3L2H", exact(stream, local_offset, 30))
        local_name = exact(stream, local_offset + 30, local[9])
        local_extra = exact(stream, local_offset + 30 + local[9], local[10])
        extras(local_extra)
        if (local[0] != b"PK\x03\x04" or local_name != name or local[1] != fields[2]
                or local[2] != fields[3] or local[3] != fields[4]
                or local[4:6] != fields[5:7] or disk != 0):
            raise ValueError()
        sizes = _resolve_zip64_extra(local_extra, local[8], local[7], 0, 0)
        if sizes is None:
            raise ValueError()
        descriptor = bool(fields[3] & 8)
        if descriptor:
            if local[6] not in (0, fields[7]) or sizes[0] not in (0, unpacked) or sizes[1] not in (0, compressed):
                raise ValueError()
        elif local[6] != fields[7] or sizes[:2] != (unpacked, compressed):
            raise ValueError()
        data_end = local_offset + 30 + local[9] + local[10] + compressed
        if data_end > central_offset:
            raise ValueError()
        records.append((local_offset, data_end, descriptor, fields[7], compressed, unpacked))
        patches.extend((local_offset + 10, central_offset + position + 12))
        position += 46 + name_length + extra_length + comment_length
    records.sort()
    if not records or records[0][0] != 0:
        raise ValueError()
    for index, (_, end_data, descriptor, crc, compressed, unpacked) in enumerate(records):
        next_offset = records[index + 1][0] if index + 1 < len(records) else central_offset
        gap = next_offset - end_data
        if not descriptor:
            if gap != 0:
                raise ValueError()
        else:
            if gap not in (12, 16, 20, 24):
                raise ValueError()
            raw = exact(stream, end_data, gap)
            if gap in (16, 24):
                if raw[:4] != b"PK\x07\x08":
                    raise ValueError()
                raw = raw[4:]
            values = struct.unpack("<LLL" if len(raw) == 12 else "<LQQ", raw)
            if values != (crc, compressed, unpacked):
                raise ValueError()
    patches.sort()
    if len(patches) != len(set(patches)) or any(b < a + 4 for a, b in zip(patches, patches[1:])):
        raise ValueError()
    return patches


def canonicalize(source, output, manifest_path, manifest_sha, package_sha, package_size):
    source = pack._safe_absolute(str(source))
    output = pack._fresh_external_output(str(output))
    manifest, _ = pack._manifest(pack._safe_absolute(str(manifest_path)), manifest_sha)
    if pack._hash_package(source) != (package_sha, package_size):
        raise ValueError()
    pack._verify_package(source, manifest)
    before = source.lstat()
    with source.open("rb") as incoming:
        opened = os.fstat(incoming.fileno())
        if not pack._same_open_file(before, opened, source.suffix):
            raise ValueError()
        patches = patch_map(incoming, package_size)
        digest = hashlib.sha256()
        with output.open("xb") as outgoing:
            position = 0
            for patch in [*patches, package_size]:
                incoming.seek(position)
                remaining = patch - position
                while remaining:
                    chunk = incoming.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError()
                    outgoing.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
                if patch != package_size:
                    outgoing.write(STAMP)
                    digest.update(STAMP)
                position = patch + 4
        if pack._leaf_snapshot(opened) != pack._leaf_snapshot(os.fstat(incoming.fileno())):
            raise ValueError()
    if pack._leaf_snapshot(before) != pack._leaf_snapshot(source.lstat()) or pack._hash_package(source) != (package_sha, package_size):
        raise ValueError()
    if pack._hash_package(output) != (digest.hexdigest(), package_size):
        raise ValueError()
    pack._verify_package(output, manifest)
    return {"contract": "unsigned-msix-timestamps.v1", "passed": True, "sha256": digest.hexdigest(),
            "size_bytes": package_size, "timestamp_fields": len(patches), "pre_sign_canonicalization": True,
            "sdk_native_reproducibility": False, "signed": False, "installed": False}


def main(argv=None):
    try:
        parser = pack._ClosedParser(add_help=False)
        for name in ("source", "output", "manifest", "manifest-sha256", "package-sha256"):
            parser.add_argument("--" + name, required=True)
        parser.add_argument("--package-size", type=int, required=True)
        args = parser.parse_args(argv)
        receipt = canonicalize(args.source, args.output, args.manifest, args.manifest_sha256, args.package_sha256, args.package_size)
    except Exception:
        receipt = {"contract": "unsigned-msix-timestamps.v1", "passed": False, "error_code": "canonicalization_failed"}
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
