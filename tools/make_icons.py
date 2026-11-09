# -*- coding: utf-8 -*-
"""
图标生成工具  —  唐完了 出品
把一张 JPG/PNG 头像转换为托盘用的多尺寸 .ico:
  icon_normal.ico  原始头像 (正常桌面状态)
  icon_pure.ico    头像 + 右下角绿色圆点 (纯净桌面状态)

仅依赖 Python 标准库 + Windows 自带 GDI+ (加载/缩放图像) + zlib (PNG 编码)。

用法: python make_icons.py <图片路径> [输出目录]
"""
import ctypes
from ctypes import wintypes as wt
import os
import struct
import sys
import zlib

gdiplus = ctypes.WinDLL("gdiplus.dll")

# ---------------- GDI+ 常量与结构 ----------------
PixelFormat32bppARGB = 0x0026200A
ImageLockModeRead = 1
InterpolationModeHighQualityBicubic = 7

class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", ctypes.c_uint32),
                ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", ctypes.c_int32),
                ("SuppressExternalCodecs", ctypes.c_int32)]

class GdiRect(ctypes.Structure):
    _fields_ = [("X", ctypes.c_int), ("Y", ctypes.c_int),
                ("Width", ctypes.c_int), ("Height", ctypes.c_int)]

class BitmapData(ctypes.Structure):
    _fields_ = [("Width", ctypes.c_uint), ("Height", ctypes.c_uint),
                ("Stride", ctypes.c_int), ("PixelFormat", ctypes.c_int),
                ("Scan0", ctypes.c_void_p), ("Reserved", ctypes.c_uint)]

def _chk(status, what):
    if status != 0:
        raise RuntimeError("GDI+ %s 失败, status=%d" % (what, status))

# ---------------- PNG 编码 (纯手写) ----------------
def _chunk(typ, data):
    return (struct.pack(">I", len(data)) + typ + data +
            struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

def png_encode(w, h, rgba):
    raw = b"".join(b"\x00" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8bit RGBA
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) +
            _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))

# ---------------- 尺寸缩放 + 取像素 ----------------
def load_pixels(src_path, size):
    """用 GDI+ 加载图片并高质量缩放到 size x size, 返回 RGBA 字节串"""
    token = ctypes.c_ulong()
    si = GdiplusStartupInput(1, None, 0, 0)  # GdiplusVersion 必须 = 1
    _chk(gdiplus.GdiplusStartup(ctypes.byref(token), ctypes.byref(si), None), "启动")

    def _finally(dispose_list):
        for fn, arg in dispose_list:
            fn(arg)
        gdiplus.GdiplusShutdown(token)

    src = ctypes.c_void_p()
    if gdiplus.GdipCreateBitmapFromFile(src_path, ctypes.byref(src)) != 0:
        _finally([])
        raise RuntimeError("无法读取图片: %s" % src_path)
    disposes = [(gdiplus.GdipDisposeImage, src)]

    try:
        dst = ctypes.c_void_p()
        _chk(gdiplus.GdipCreateBitmapFromScan0(size, size, 0, PixelFormat32bppARGB,
                                               None, ctypes.byref(dst)), "建位图")
        disposes.append((gdiplus.GdipDisposeImage, dst))
        gfx = ctypes.c_void_p()
        _chk(gdiplus.GdipGetImageGraphicsContext(dst, ctypes.byref(gfx)), "取画布")
        disposes.append((gdiplus.GdipDeleteGraphics, gfx))
        gdiplus.GdipSetInterpolationMode(gfx, InterpolationModeHighQualityBicubic)
        _chk(gdiplus.GdipDrawImageRectI(gfx, src, 0, 0, size, size), "缩放")

        rect = GdiRect(0, 0, size, size)
        bd = BitmapData()
        _chk(gdiplus.GdipBitmapLockBits(dst, ctypes.byref(rect), ImageLockModeRead,
                                        PixelFormat32bppARGB, ctypes.byref(bd)), "锁位图")
        try:
            mem = ctypes.string_at(bd.Scan0, bd.Stride * bd.Height)
        finally:
            gdiplus.GdipBitmapUnlockBits(dst, ctypes.byref(bd))

        rgba = bytearray(size * size * 4)
        for y in range(size):
            row = y * size * 4
            src_row = y * bd.Stride
            for x in range(size):
                b0, g0, r0, a0 = mem[src_row + x * 4: src_row + x * 4 + 4]
                rgba[row + x * 4] = r0
                rgba[row + x * 4 + 1] = g0
                rgba[row + x * 4 + 2] = b0
                rgba[row + x * 4 + 3] = a0
        return bytes(rgba)
    finally:
        _finally(disposes)

def add_badge(rgba, size):
    """右下角加 纯净模式 徽标: 白圈 + 绿点"""
    cx, cy = size * 0.72, size * 0.72
    r_ring = size * 0.26   # 白色外圈半径
    r_dot = size * 0.17    # 绿色内点半径
    G, RING = (0x22, 0xC5, 0x5E), (0xFF, 0xFF, 0xFF)  # RGB
    for y in range(size):
        for x in range(size):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if d <= r_dot:
                c, a = G, 255
            elif d <= r_ring:
                c, a = RING, 255
            else:
                continue
            i = (y * size + x) * 4
            rgba[i], rgba[i + 1], rgba[i + 2], rgba[i + 3] = c[0], c[1], c[2], a
    return rgba

# ---------------- ICO 容器 ----------------
def make_ico(entries):
    """entries = [(size, png_bytes)]; PNG 压缩条目, Vista+ 全支持"""
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    dirs, blobs = b"", b""
    for size, data in entries:
        s = 0 if size >= 256 else size
        dirs += struct.pack("<BBBBHHII", s, s, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return header + dirs + blobs

SIZES = [16, 24, 32, 48, 64, 128, 256]

def build_icons(src_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    normal, pure = [], []
    for s in SIZES:
        px = bytearray(load_pixels(src_path, s))
        normal.append((s, png_encode(s, s, bytes(px))))
        pure.append((s, png_encode(s, s, add_badge(px, s))))
        print("已生成 %dx%d" % (s, s))
    p1 = os.path.join(out_dir, "icon_normal.ico")
    p2 = os.path.join(out_dir, "icon_pure.ico")
    with open(p1, "wb") as f:
        f.write(make_ico(normal))
    with open(p2, "wb") as f:
        f.write(make_ico(pure))
    print("完成:", p1)
    print("完成:", p2)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "icons")
    build_icons(src, os.path.abspath(out))
