import os
from typing import Tuple, Union, List
from PIL import Image, ImageFont, ImageDraw

from src.liteyuki_api.config import Path


class BasePanel:
    def __init__(self,
                 uv_size: Tuple[Union[int, float], Union[int, float]] = (1.0, 1.0),
                 box_size: Tuple[Union[int, float], Union[int, float]] = (1.0, 1.0),
                 parent_point: Tuple[float, float] = (0.5, 0.5),
                 point: Tuple[float, float] = (0.5, 0.5)):
        """
        :param uv_size: 底面板大小
        :param box_size: 子（自身）面板大小
        :param parent_point: 底面板锚点
        :param point: 子（自身）面板锚点
        """
        self.canvas: "Canvas" = None
        self.uv_size = uv_size
        self.box_size = box_size
        self.parent_point = parent_point
        self.point = point
        # 此节点在父节点上的盒子
        self.box = (
            self.parent_point[0] - self.point[0] * self.box_size[0] / self.uv_size[0],
            self.parent_point[1] - self.point[1] * self.box_size[1] / self.uv_size[1],
            self.parent_point[0] + (1 - self.point[0]) * self.box_size[0] / self.uv_size[0],
            self.parent_point[1] + (1 - self.point[1]) * self.box_size[1] / self.uv_size[1]
        )

    def load(self, canvas_box):
        """
        将对象写入画布
        此处仅作声明
        由各子类重写
        :param canvas_box:
        :return:
        """
        pass

    def save_as(self, canvas_box):
        """
        此函数执行时间较长，建议异步运行
        :param canvas_box 此节点在画布上的盒子,并不是在父节点上的盒子
        :return:
        """
        for name, child in self.__dict__.items():
            # 此节点在画布上的盒子
            if isinstance(child, BasePanel) and name != "canvas":
                if isinstance(self, Canvas):
                    child.canvas = self
                else:
                    child.canvas = self.canvas
                dxc = canvas_box[2] - canvas_box[0]
                dyc = canvas_box[3] - canvas_box[1]
                child_canvas_box = (
                    canvas_box[0] + dxc * child.box[0],
                    canvas_box[1] + dyc * child.box[1],
                    canvas_box[0] + dxc * child.box[2],
                    canvas_box[1] + dyc * child.box[3]
                )
                child.load(child_canvas_box)
                child.save_as(child_canvas_box)


class Canvas(BasePanel):
    def __init__(self, base_img: Image.Image):
        self.base_img = base_img
        super(Canvas, self).__init__()

    def export(self, file):
        self.base_img = self.base_img.convert("RGBA")
        self.save_as((0, 0, 1, 1))
        self.base_img.save(file)


class Panel(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point):
        super(Panel, self).__init__(uv_size, box_size, parent_point, point)


class Text(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point, text, font, color, vertical=False, line_feed=False, force_size=False, dp: int = 5):
        """
        :param uv_size:
        :param box_size:
        :param parent_point:
        :param point:
        :param text:
        :param font:
        :param color:
        :param vertical: 是否竖直
        :param line_feed: 是否换行
        :param force_size: 强制大小
        :param dp: 字体大小递减精度
        """
        self.font = font
        self.text = text
        self.color = color
        self.force_size = force_size
        self.vertical = vertical
        self.line_feed = line_feed
        self.dp = dp
        super(Text, self).__init__(uv_size, box_size, parent_point, point)

    def load(self, canvas_box):
        """限制区域像素大小"""
        limited_size = int((canvas_box[2] - canvas_box[0]) * self.canvas.base_img.size[0]), int((canvas_box[3] - canvas_box[1]) * self.canvas.base_img.size[1])
        font_size = limited_size[1]
        image_font = ImageFont.truetype(self.font, font_size)
        actual_size = image_font.getsize(self.text)
        while (actual_size[0] > limited_size[0] or actual_size[1] > limited_size[1]) and not self.force_size:
            font_size -= self.dp
            image_font = ImageFont.truetype(self.font, font_size)
            actual_size = image_font.getsize(self.text)
        draw = ImageDraw.Draw(self.canvas.base_img)
        start_point = (
            int(self.canvas.base_img.size[0] * (canvas_box[0] + canvas_box[2]) / 2 - actual_size[0] / 2),
            int(self.canvas.base_img.size[1] * (canvas_box[1] + canvas_box[3]) / 2 - actual_size[1] / 2)
        )
        draw.text(start_point, self.text, self.color, font=image_font)
        self.actual_pos = (
            start_point[0] / self.canvas.base_img.size[0],
            start_point[1] / self.canvas.base_img.size[1],
            (start_point[0] + actual_size[0]) / self.canvas.base_img.size[0],
            (start_point[1] + actual_size[1]) / self.canvas.base_img.size[1],
        )

    def get_actual_size(self) -> Tuple[float, float, float, float]:
        """
        函数执行时间较长，推荐异步执行
        :return:
        """
        self.canvas.save_as((0, 0, 1, 1))
        return self.actual_pos


class Img(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point, img: Image.Image, keep_ratio=True):
        self.img = img
        self.keep_ratio = keep_ratio
        super(Img, self).__init__(uv_size, box_size, parent_point, point)

    def load(self, canvas_box):
        self.img = self.img.convert("RGBA")
        limited_size = int((canvas_box[2] - canvas_box[0]) * self.canvas.base_img.size[0]), int((canvas_box[3] - canvas_box[1]) * self.canvas.base_img.size[1])
        if self.keep_ratio:

            actual_ratio = self.img.size[0] / self.img.size[1]
            limited_ratio = limited_size[0] / limited_size[1]
            if actual_ratio > limited_ratio:
                # 图片过长
                self.img = self.img.resize(
                    (int(self.img.size[0] * limited_size[0] / self.img.size[0]),
                     int(self.img.size[1] * limited_size[0] / self.img.size[0]))
                )
            else:
                self.img = self.img.resize(
                    (int(self.img.size[0] * limited_size[1] / self.img.size[1]),
                     int(self.img.size[1] * limited_size[1] / self.img.size[1]))
                )

        else:
            self.img = self.img.resize(limited_size)
        start_point = (
            int(self.canvas.base_img.size[0] * (canvas_box[0] + canvas_box[2]) / 2 - self.img.size[0] / 2),
            int(self.canvas.base_img.size[1] * (canvas_box[1] + canvas_box[3]) / 2 - self.img.size[1] / 2)
        )
        alpha = self.img.split()[3]
        self.actual_pos = (
            start_point[0] / self.canvas.base_img.size[0],
            start_point[1] / self.canvas.base_img.size[1],
            (start_point[0] + self.img.size[0]) / self.canvas.base_img.size[0],
            (start_point[1] + self.img.size[1]) / self.canvas.base_img.size[1],
        )
        self.canvas.base_img.paste(self.img, start_point, alpha)

    def get_actual_size(self) -> Tuple[float, float, float, float]:
        """
                函数执行时间较长，推荐异步执行
                :return:
                """
        self.canvas.save_as((0, 0, 1, 1))
        return self.actual_pos