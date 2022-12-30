import os
import uuid
import textwrap
from typing import Tuple, Union, List
from PIL import Image, ImageFont, ImageDraw

from .config import Path

default_color = (255, 255, 255, 255)


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
        self.parent: BasePanel = None
        self.canvas_box: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
        # 此节点在父节点上的盒子
        self.box = (
            self.parent_point[0] - self.point[0] * self.box_size[0] / self.uv_size[0],
            self.parent_point[1] - self.point[1] * self.box_size[1] / self.uv_size[1],
            self.parent_point[0] + (1 - self.point[0]) * self.box_size[0] / self.uv_size[0],
            self.parent_point[1] + (1 - self.point[1]) * self.box_size[1] / self.uv_size[1]
        )

    def load(self, only_calculate=False):
        """
        将对象写入画布
        此处仅作声明
        由各子类重写

        :return:
        """
        self.actual_pos = self.canvas_box

    def save_as(self, canvas_box, only_calculate=False):
        """
        此函数执行时间较长，建议异步运行
        :param only_calculate:
        :param canvas_box 此节点在画布上的盒子,并不是在父节点上的盒子
        :return:
        """
        for name, child in self.__dict__.items():
            # 此节点在画布上的盒子
            if isinstance(child, BasePanel) and name not in ["canvas", "parent"]:
                child.parent = self
                if isinstance(self, Canvas):
                    child.canvas = self
                else:
                    child.canvas = self.canvas
                dxc = canvas_box[2] - canvas_box[0]
                dyc = canvas_box[3] - canvas_box[1]
                child.canvas_box = (
                    canvas_box[0] + dxc * child.box[0],
                    canvas_box[1] + dyc * child.box[1],
                    canvas_box[0] + dxc * child.box[2],
                    canvas_box[1] + dyc * child.box[3]
                )
                child.load(only_calculate)
                child.save_as(child.canvas_box, only_calculate)


class Canvas(BasePanel):
    def __init__(self, base_img: Image.Image):
        self.base_img = base_img
        self.canvas = self
        super(Canvas, self).__init__()

    def export(self, file, alpha=False):
        self.base_img = self.base_img.convert("RGBA")
        self.save_as((0, 0, 1, 1))
        if not alpha:
            self.base_img = self.base_img.convert("RGB")
        self.base_img.save(file)

    def export_cache(self, alpha=False) -> str:
        """
        随机文件名储存

        :return:
        """
        file = os.path.join(Path.cache, "%s.png" % str(uuid.uuid4()))
        self.export(file, alpha)
        self.file = file
        return file

    def delete(self):
        os.remove(self.file)

    def get_actual_box(self, path: str) -> Union[None, Tuple[float, float, float, float]]:
        """
        获取控件实际相对大小
        函数执行时间较长

        :param path: 控件路径
        :return:
        """
        sub_obj = self
        self.save_as((0, 0, 1, 1), True)
        try:
            for i, seq in enumerate(path.split(".")):
                sub_obj = sub_obj.__dict__[seq]
            return sub_obj.actual_pos
        except KeyError:
            raise KeyError("检查一下是不是控件路径写错力")

    def get_actual_pixel_size(self, path: str) -> Union[None, Tuple[int, int]]:
        """
        获取控件实际像素长宽
        函数执行时间较长
        :param path: 控件路径
        :return:
        """
        sub_obj = self
        self.save_as((0, 0, 1, 1), True)
        try:
            for i, seq in enumerate(path.split(".")):
                sub_obj = sub_obj.__dict__[seq]
            dx = int(sub_obj.canvas.base_img.size[0] * (sub_obj.actual_pos[2] - sub_obj.actual_pos[0]))
            dy = int(sub_obj.canvas.base_img.size[1] * (sub_obj.actual_pos[3] - sub_obj.actual_pos[1]))
            return dx, dy
        except KeyError:
            raise KeyError("检查一下是不是控件路径写错力")

    def get_actual_pixel_box(self, path: str) -> Union[None, Tuple[int, int, int, int]]:
        """
        获取控件实际像素大小盒子
        函数执行时间较长
        :param path: 控件路径
        :return:
        """
        sub_obj = self
        self.save_as((0, 0, 1, 1), True)
        try:
            for i, seq in enumerate(path.split(".")):
                sub_obj = sub_obj.__dict__[seq]
            x1 = int(sub_obj.canvas.base_img.size[0] * sub_obj.actual_pos[0])
            y1 = int(sub_obj.canvas.base_img.size[1] * sub_obj.actual_pos[1])
            x2 = int(sub_obj.canvas.base_img.size[2] * sub_obj.actual_pos[2])
            y2 = int(sub_obj.canvas.base_img.size[3] * sub_obj.actual_pos[3])
            return x1, y1, x2, y2
        except KeyError:
            raise KeyError("检查一下是不是控件路径写错力")

    def get_parent_box(self, path: str) -> Union[None, Tuple[float, float, float, float]]:
        """
                获取控件在父节点的大小
                函数执行时间较长

                :param path: 控件路径
                :return:
                """
        sub_obj = self.get_control_by_path(path)
        on_parent_pos = (
            (sub_obj.actual_pos[0] - sub_obj.parent.actual_pos[0]) / (sub_obj.parent.actual_pos[2] - sub_obj.parent.actual_pos[0]),
            (sub_obj.actual_pos[1] - sub_obj.parent.actual_pos[1]) / (sub_obj.parent.actual_pos[3] - sub_obj.parent.actual_pos[1]),
            (sub_obj.actual_pos[2] - sub_obj.parent.actual_pos[0]) / (sub_obj.parent.actual_pos[2] - sub_obj.parent.actual_pos[0]),
            (sub_obj.actual_pos[3] - sub_obj.parent.actual_pos[1]) / (sub_obj.parent.actual_pos[3] - sub_obj.parent.actual_pos[1])
        )
        return on_parent_pos

    def get_control_by_path(self, path: str) -> Union[BasePanel, "Img", "Rectangle", "Text"]:
        sub_obj = self
        self.save_as((0, 0, 1, 1), True)
        try:
            for i, seq in enumerate(path.split(".")):
                sub_obj = sub_obj.__dict__[seq]
            return sub_obj
        except KeyError:
            raise KeyError("检查一下是不是控件路径写错力")

    def draw_line(self, path: str, p1: Tuple[float, float], p2: Tuple[float, float], color, width):
        """
        画线

        :param color:
        :param width:
        :param path:
        :param p1:
        :param p2:
        :return:
        """
        ac_pos = self.get_actual_box(path)
        control = self.get_control_by_path(path)
        dx = ac_pos[2] - ac_pos[0]
        dy = ac_pos[3] - ac_pos[1]
        xy_box = int((ac_pos[0] + dx * p1[0]) * control.canvas.base_img.size[0]), int((ac_pos[1] + dy * p1[1]) * control.canvas.base_img.size[1]), int(
            (ac_pos[0] + dx * p2[0]) * control.canvas.base_img.size[0]), int((ac_pos[1] + dy * p2[1]) * control.canvas.base_img.size[1])
        draw = ImageDraw.Draw(control.canvas.base_img)
        draw.line(xy_box, color, width)


class Panel(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point):
        super(Panel, self).__init__(uv_size, box_size, parent_point, point)


class TextSegment:
    def __init__(self, text, **kwargs):
        self.text = text
        self.color = kwargs.get("color", None)
        self.font = kwargs.get("font", None)

    @staticmethod
    def text2text_segment_list(text: str):
        """
        暂时没写好

        :param text: %FFFFFFFF%1123%FFFFFFFF%21323
        :return:
        """
        pass


class Text(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point, text: Union[str, list], font=os.path.join(Path.res, "fonts/default.ttf"), color=(255, 255, 255, 255), vertical=False,
                 line_feed=False, force_size=False, font_size=None, dp: int = 5):
        """
        :param uv_size:
        :param box_size:
        :param parent_point:
        :param point:
        :param text: list[{"text": "A", "color":(200,200,200,200)}]
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
        self.font_size = font_size
        super(Text, self).__init__(uv_size, box_size, parent_point, point)

    def load(self, only_calculate=False):
        """限制区域像素大小"""
        if isinstance(self.text, str):
            self.text = [
                TextSegment(text=self.text, color=self.color, font=self.font)
            ]
        all_text = str()
        for text in self.text:
            all_text += text.text
        limited_size = int((self.canvas_box[2] - self.canvas_box[0]) * self.canvas.base_img.size[0]), int((self.canvas_box[3] - self.canvas_box[1]) * self.canvas.base_img.size[1])
        font_size = limited_size[1] if self.font_size is None else self.font_size
        image_font = ImageFont.truetype(self.font, font_size)
        actual_size = image_font.getsize(all_text)
        while (actual_size[0] > limited_size[0] or actual_size[1] > limited_size[1]) and not self.force_size:
            font_size -= self.dp
            image_font = ImageFont.truetype(self.font, font_size)
            actual_size = image_font.getsize(all_text)
        draw = ImageDraw.Draw(self.canvas.base_img)
        if isinstance(self.parent, Img) or isinstance(self.parent, Text):
            self.parent.canvas_box = self.parent.actual_pos
        dx0 = self.parent.canvas_box[2] - self.parent.canvas_box[0]
        dy0 = self.parent.canvas_box[3] - self.parent.canvas_box[1]
        dx1 = actual_size[0] / self.canvas.base_img.size[0]
        dy1 = actual_size[1] / self.canvas.base_img.size[1]
        start_point = [
            int((self.parent.canvas_box[0] + dx0 * self.parent_point[0] - dx1 * self.point[0]) * self.canvas.base_img.size[0]),
            int((self.parent.canvas_box[1] + dy0 * self.parent_point[1] - dy1 * self.point[1]) * self.canvas.base_img.size[1])
        ]
        self.actual_pos = (
            start_point[0] / self.canvas.base_img.size[0],
            start_point[1] / self.canvas.base_img.size[1],
            (start_point[0] + actual_size[0]) / self.canvas.base_img.size[0],
            (start_point[1] + actual_size[1]) / self.canvas.base_img.size[1],
        )
        self.font_size = font_size
        if not only_calculate:
            for text_segment in self.text:
                if text_segment.color is None:
                    text_segment.color = self.color
                if text_segment.font is None:
                    text_segment.font = self.font
                image_font = ImageFont.truetype(font=text_segment.font, size=font_size)
                draw.text(start_point, text_segment.text, text_segment.color, font=image_font)
                text_width = image_font.getsize(text_segment.text)
                start_point[0] += text_width[0]


class Img(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point, img: Image.Image, keep_ratio=True):
        self.img = img
        self.keep_ratio = keep_ratio
        super(Img, self).__init__(uv_size, box_size, parent_point, point)

    def load(self, only_calculate=False):
        self.preprocess()
        self.img = self.img.convert("RGBA")
        limited_size = int((self.canvas_box[2] - self.canvas_box[0]) * self.canvas.base_img.size[0]), \
                       int((self.canvas_box[3] - self.canvas_box[1]) * self.canvas.base_img.size[1])

        if self.keep_ratio:
            """保持比例"""
            actual_ratio = self.img.size[0] / self.img.size[1]
            limited_ratio = limited_size[0] / limited_size[1]
            if actual_ratio >= limited_ratio:
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
            """不保持比例"""
            self.img = self.img.resize(limited_size)

        # 占比长度
        if isinstance(self.parent, Img) or isinstance(self.parent, Text):
            self.parent.canvas_box = self.parent.actual_pos

        dx0 = self.parent.canvas_box[2] - self.parent.canvas_box[0]
        dy0 = self.parent.canvas_box[3] - self.parent.canvas_box[1]

        dx1 = self.img.size[0] / self.canvas.base_img.size[0]
        dy1 = self.img.size[1] / self.canvas.base_img.size[1]
        start_point = (
            int((self.parent.canvas_box[0] + dx0 * self.parent_point[0] - dx1 * self.point[0]) * self.canvas.base_img.size[0]),
            int((self.parent.canvas_box[1] + dy0 * self.parent_point[1] - dy1 * self.point[1]) * self.canvas.base_img.size[1])
        )
        alpha = self.img.split()[3]
        self.actual_pos = (
            start_point[0] / self.canvas.base_img.size[0],
            start_point[1] / self.canvas.base_img.size[1],
            (start_point[0] + self.img.size[0]) / self.canvas.base_img.size[0],
            (start_point[1] + self.img.size[1]) / self.canvas.base_img.size[1],
        )
        if not only_calculate:
            self.canvas.base_img.paste(self.img, start_point, alpha)

    def preprocess(self):
        pass


class Rectangle(Img):
    def __init__(self, uv_size, box_size, parent_point, point, fillet: Union[int, float] = 0, img: Union[Image.Image] = None, keep_ratio=True,
                 color=default_color, outline_width=0, outline_color=default_color):
        """
        圆角图
        :param uv_size:
        :param box_size:
        :param parent_point:
        :param point:
        :param fillet: 圆角半径浮点或整数
        :param img:
        :param keep_ratio:
        """
        self.fillet = fillet
        self.color = color
        self.outline_width = outline_width
        self.outline_color = outline_color
        super(Rectangle, self).__init__(uv_size, box_size, parent_point, point, img, keep_ratio)

    def preprocess(self):
        limited_size = (int(self.canvas.base_img.size[0] * (self.canvas_box[2] - self.canvas_box[0])),
                        int(self.canvas.base_img.size[1] * (self.canvas_box[3] - self.canvas_box[1])))
        if not self.keep_ratio and self.img is not None and self.img.size[0] / self.img.size[1] != limited_size[0] / limited_size[1]:
            self.img = self.img.resize(limited_size)
        self.img = Graphical.rectangle(size=limited_size, fillet=self.fillet, color=self.color, outline_width=self.outline_width, outline_color=self.outline_color, img=self.img)


class Color:
    GREY = (128, 128, 128, 255)
    RED = (255, 0, 0, 255)
    GREEN = (0, 255, 0, 255)
    BLUE = (0, 0, 255, 255)
    YELLOW = (255, 255, 0, 0)
    PURPLE = (255, 0, 255, 0)
    CYAN = (0, 255, 255, 0)
    WHITE = (255, 255, 255, 255)
    BLACK = (0, 0, 0, 255)

    @staticmethod
    def hex2dec(colorHex: str) -> Tuple[int, int, int, int]:
        """
        :param colorHex: FFFFFFFF （ARGB）-> (R, G, B, A)
        :return:
        """
        return int(colorHex[2:4], 16), int(colorHex[4:6], 16), int(colorHex[6:8], 16), int(colorHex[0:2], 16)


class Graphical:

    @staticmethod
    def circular(r, color=default_color, outline_width=0, outline_color=default_color, img=None) -> Image.Image:
        base = img
        if img is None:
            base = Image.new(mode="RGBA", color=(0, 0, 0, 0), size=(r, r))
        draw = ImageDraw.Draw(base)
        draw.ellipse(xy=(0, 0, r, r), fill=color, width=outline_width, outline=outline_color)
        return base

    @staticmethod
    def ellipse(size, color=default_color, outline_width=0, outline_color=default_color, img=None) -> Image.Image:
        base = img
        if img is None:
            base = Image.new(mode="RGBA", color=(0, 0, 0, 0), size=size)
        draw = ImageDraw.Draw(base)
        draw.ellipse(xy=(0, 0, size[0], size[1]), fill=color, width=outline_width, outline=outline_color)
        return base

    @staticmethod
    def rectangle(size, fillet: Union[int, float] = 0.0, color=default_color, outline_width=0, outline_color=default_color, img=None):
        """
        :param img:
        :param size:
        :param fillet: 圆角半径可以为0-1浮点或者整数,浮点时取宽高中最小值计算半径
        :param color:
        :param outline_width:
        :param outline_color:
        :return:
        """
        base = img
        if img is None:
            base = Image.new(mode="RGBA", color=(0, 0, 0, 0), size=size)
        draw = ImageDraw.Draw(base)
        if isinstance(fillet, float) and 0 <= fillet <= 0.5:
            r = min(size[0], size[1]) * fillet
        else:
            r = fillet
        draw.rounded_rectangle(xy=(0, 0, size[0], size[1]), radius=r, fill=color, width=outline_width, outline=outline_color)
        return base
