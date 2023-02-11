from PIL import Image

from ...liteyuki_api.utils import clamp


def wish_img_crop(img: Image.Image):
    w, h = img.size
    if w > h:
        img = img.crop(((w - h) // 2, 0, (w + h) // 2, h))
    elif w < h:
        img = img.crop((0, (h - w) // 2, w, (h + w) // 2))
    img = img.convert("RGBA")
    img = img.resize((1000, 1000))
    x_size = 320
    up_size, down_size = 100, 150
    for x in range(img.size[0]):
        for y in range(img.size[1]):
            if x in range(0, x_size) or x in range(img.size[0] - x_size, img.size[0]):
                p = list(img.getpixel((x, y)))
                """距离边缘的距离"""
                cd = min(abs(x), abs(x - img.size[0]))
                light = clamp(cd / x_size, 0, 1)
                p[3] = int(p[3] * light ** 2)
                img.putpixel((x, y), tuple(p))
            if y in range(0, up_size):
                p = list(img.getpixel((x, y)))
                """距离边缘的距离"""
                cd = y
                light = clamp(cd / up_size, 0, 1)
                p[3] = int(p[3] * light ** 2)
                img.putpixel((x, y), tuple(p))
            if y in range(img.size[1] - down_size, img.size[1]):
                p = list(img.getpixel((x, y)))
                """距离边缘的距离"""
                cd = abs(img.size[1] - y)
                light = clamp(cd / down_size, 0, 1)
                p[3] = int(p[3] * light ** 2)
                img.putpixel((x, y), tuple(p))

    return img