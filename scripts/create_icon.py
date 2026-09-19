"""生成不依赖第三方库的应用 ICO 资源。"""

from __future__ import annotations

import struct
from pathlib import Path


def pixel(size: int, x: int, y: int) -> tuple[int, int, int, int]:
    """绘制应用图标中的渐变背景和白色标记。"""
    edge = max(1, size // 8)
    if x < edge or y < edge or x >= size - edge or y >= size - edge:
        alpha = 0 if (x < edge and y < edge) or (x >= size - edge and y < edge) or (x < edge and y >= size - edge) or (x >= size - edge and y >= size - edge) else 255
    else:
        alpha = 255
    ratio = (x + y) / max(1, size * 2)
    red = int(119 - 45 * ratio)
    green = int(116 - 45 * ratio)
    blue = int(245 - 45 * ratio)
    center = size // 2
    bar_width = max(2, size // 9)
    left = center - size // 5
    middle = center
    right = center + size // 5
    for bar_x, bar_height in ((left, int(size * 0.48)), (middle, int(size * 0.72)), (right, int(size * 0.35))):
        if abs(x - bar_x) <= bar_width and center - bar_height // 2 <= y <= center + bar_height // 2:
            red, green, blue = 255, 255, 255
    return blue, green, red, alpha


def dib(size: int) -> bytes:
    """生成一个 32 位 BGRA DIB 图像。"""
    rows = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            rows.extend(pixel(size, x, y))
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    return header + rows + bytes(((size + 31) // 32) * 4 * size)


def write_icon(path: Path) -> None:
    """写入 16、32、48、256 四种尺寸的 ICO 文件。"""
    images = [dib(size) for size in (16, 32, 48, 256)]
    directory = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, image in zip((16, 32, 48, 256), images):
        directory.extend(struct.pack("<BBBBHHII", 0 if size == 256 else size, 0 if size == 256 else size, 0, 0, 1, 32, len(image), offset))
        offset += len(image)
    path.write_bytes(directory + b"".join(images))


if __name__ == "__main__":
    write_icon(Path(__file__).resolve().parents[1] / "resources" / "app.ico")

