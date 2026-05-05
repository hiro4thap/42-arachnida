import argparse
import json
import os
import struct
from typing import Dict, Tuple, Any, List, Optional

# image files' extensions can be .jpg / .jpeg / .png / .gif / .bmp

# TIFF type sizes
_TYPE_SIZES = {
    1: 1,   # BYTE
    2: 1,   # ASCII
    3: 2,   # SHORT
    4: 4,   # LONG
    5: 8,   # RATIONAL
    7: 1,   # UNDEFINED
    9: 4,   # SLONG
    10: 8,  # SRATIONAL
}

# Common EXIF tag names (partial; unknown tags will be kept as hex keys)
_TAGS = {
    0x010F: "Make",
    0x0110: "Model",
    0x0112: "Orientation",
    0x0131: "Software",
    0x0132: "DateTime",
    0x8769: "ExifIFDPointer",
    0x8825: "GPSIFDPointer",
    0x829A: "ExposureTime",
    0x829D: "FNumber",
    0x9003: "DateTimeOriginal",
    0x9004: "DateTimeDigitized",
    0x9201: "ShutterSpeedValue",
    0x9202: "ApertureValue",
    0x9209: "Flash",
    0x920A: "FocalLength",
    0xA002: "PixelXDimension",
    0xA003: "PixelYDimension",
    0x010E: "ImageDescription",
    0x0100: "ImageWidth",
    0x0101: "ImageLength",
    0x8827: "ISOSpeedRatings",
    0xA405: "FocalLengthIn35mmFilm",
    0xA406: "SceneCaptureType",
    0xA407: "GainControl",
    0xA408: "Contrast",
    0xA409: "Saturation",
    0xA40A: "Sharpness",
    0xA402: "ExposureMode",
    0xA403: "WhiteBalance",
    0xA217: "SensingMethod",
    0xA301: "SceneType",
    0xA401: "CustomRendered",
    0x8822: "ExposureProgram",
    0x9207: "MeteringMode",
    0x9208: "LightSource",
    0xA005: "InteroperabilityIFDPointer",
}

_GPS_TAGS = {
    0x0000: "GPSVersionID",
    0x0001: "GPSLatitudeRef",
    0x0002: "GPSLatitude",
    0x0003: "GPSLongitudeRef",
    0x0004: "GPSLongitude",
    0x0005: "GPSAltitudeRef",
    0x0006: "GPSAltitude",
    0x001D: "GPSDateStamp",
    0x0007: "GPSTimeStamp",
}

_INTEROP_TAGS = {
    0x0001: "InteroperabilityIndex",
    0x0002: "InteroperabilityVersion",
}


def _read_u16(data: bytes, offset: int, endian: str) -> int:
    return struct.unpack_from(endian + "H", data, offset)[0]


def _read_u32(data: bytes, offset: int, endian: str) -> int:
    return struct.unpack_from(endian + "I", data, offset)[0]


def _read_i32(data: bytes, offset: int, endian: str) -> int:
    return struct.unpack_from(endian + "i", data, offset)[0]


def _safe_slice(data: bytes, offset: int, length: int) -> bytes:
    if offset < 0 or offset + length > len(data):
        return b""
    return data[offset:offset + length]


def _extract_exif_segment(jpeg: bytes) -> Optional[bytes]:
    # JPEG starts with 0xFFD8
    if len(jpeg) < 4 or jpeg[0:2] != b"\xFF\xD8":
        return None
    i = 2
    while i + 4 <= len(jpeg):
        if jpeg[i] != 0xFF:
            i += 1
            continue
        marker = jpeg[i + 1]
        # EOI or SOS -> stop
        if marker == 0xD9 or marker == 0xDA:
            break
        # stand-alone markers
        if marker in (0x01,) or (0xD0 <= marker <= 0xD7):
            i += 2
            continue
        seg_len = struct.unpack_from(">H", jpeg, i + 2)[0]
        seg_start = i + 4
        seg_end = seg_start + seg_len - 2
        if seg_end > len(jpeg):
            break
        if marker == 0xE1:  # APP1
            seg = jpeg[seg_start:seg_end]
            if seg.startswith(b"Exif\x00\x00"):
                return seg[6:]
        i = seg_end
    return None


def _decode_value(data: bytes, tiff_base: int, endian: str, type_id: int, count: int, value_offset: int) -> Any:
    type_size = _TYPE_SIZES.get(type_id, 1)
    total_size = type_size * count
    if total_size <= 4:
        value_data = struct.pack(endian + "I", value_offset)[:total_size]
    else:
        value_data = _safe_slice(data, tiff_base + value_offset, total_size)

    if type_id == 1 or type_id == 7:  # BYTE/UNDEFINED
        return list(value_data) if count > 1 else (value_data[0] if value_data else None)
    if type_id == 2:  # ASCII
        return value_data.rstrip(b"\x00").decode("latin1", errors="replace")
    if type_id == 3:  # SHORT
        fmt = endian + ("H" * count)
        return list(struct.unpack(fmt, value_data)) if count > 1 else struct.unpack(fmt, value_data)[0]
    if type_id == 4:  # LONG
        fmt = endian + ("I" * count)
        return list(struct.unpack(fmt, value_data)) if count > 1 else struct.unpack(fmt, value_data)[0]
    if type_id == 5:  # RATIONAL
        vals = []
        for idx in range(count):
            num = _read_u32(value_data, idx * 8, endian)
            den = _read_u32(value_data, idx * 8 + 4, endian)
            vals.append([num, den])
        return vals if count > 1 else vals[0]
    if type_id == 9:  # SLONG
        fmt = endian + ("i" * count)
        return list(struct.unpack(fmt, value_data)) if count > 1 else struct.unpack(fmt, value_data)[0]
    if type_id == 10:  # SRATIONAL
        vals = []
        for idx in range(count):
            num = _read_i32(value_data, idx * 8, endian)
            den = _read_i32(value_data, idx * 8 + 4, endian)
            vals.append([num, den])
        return vals if count > 1 else vals[0]
    return value_data


def _parse_ifd(
    data: bytes,
    tiff_base: int,
    offset: int,
    endian: str,
    tag_map: Dict[int, str],
    exif: Dict[str, Any],
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    if offset <= 0 or tiff_base + offset + 2 > len(data):
        return None, None, None
    count = _read_u16(data, tiff_base + offset, endian)
    pos = tiff_base + offset + 2
    exif_ifd = None
    gps_ifd = None
    interop_ifd = None

    for _ in range(count):
        if pos + 12 > len(data):
            break
        tag = _read_u16(data, pos, endian)
        type_id = _read_u16(data, pos + 2, endian)
        count_v = _read_u32(data, pos + 4, endian)
        value_offset = _read_u32(data, pos + 8, endian)

        value = _decode_value(data, tiff_base, endian, type_id, count_v, value_offset)
        name = tag_map.get(tag, f"tag_0x{tag:04X}")
        exif[name] = value

        if tag == 0x8769:
            exif_ifd = value_offset
        elif tag == 0x8825:
            gps_ifd = value_offset
        elif tag == 0xA005:
            interop_ifd = value_offset

        pos += 12

    next_ifd_offset = _read_u32(data, pos, endian) if pos + 4 <= len(data) else None
    return exif_ifd, gps_ifd, interop_ifd


def _parse_exif_from_app1(exif_data: bytes) -> Dict[str, Any]:
    if len(exif_data) < 8:
        return {}

    endian_bytes = exif_data[0:2]
    if endian_bytes == b"II":
        endian = "<"
    elif endian_bytes == b"MM":
        endian = ">"
    else:
        return {}

    tiff_magic = _read_u16(exif_data, 2, endian)
    if tiff_magic != 0x002A:
        return {}

    ifd0_offset = _read_u32(exif_data, 4, endian)
    exif: Dict[str, Any] = {}

    exif_ifd, gps_ifd, interop_ifd = _parse_ifd(
        exif_data, 0, ifd0_offset, endian, _TAGS, exif
    )

    if exif_ifd:
        _parse_ifd(exif_data, 0, exif_ifd, endian, _TAGS, exif)
    if gps_ifd:
        _parse_ifd(exif_data, 0, gps_ifd, endian, _GPS_TAGS, exif)
    if interop_ifd:
        _parse_ifd(exif_data, 0, interop_ifd, endian, _INTEROP_TAGS, exif)

    return exif


def _extract_exif(path: str) -> Tuple[Dict[str, Any], Optional[str]]:
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".bmp"):
        return {}, "unsupported extension"

    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return {}, f"read error: {e}"

    if ext in (".png", ".gif", ".bmp"):
        return {}, "EXIF not supported for this format without external libraries"

    app1 = _extract_exif_segment(data)
    if not app1:
        return {}, "no EXIF data found"

    exif = _parse_exif_from_app1(app1)
    return exif, None


def main():
    parser = argparse.ArgumentParser(description="Extract EXIF data from image files (no external libs).")
    parser.add_argument("files", nargs="+", help="Image file paths")
    args = parser.parse_args()

    for path in args.files:
        exif, error = _extract_exif(path)
        out = {"file": path, "exif": exif}
        if error:
            out["error"] = error
        print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    main()