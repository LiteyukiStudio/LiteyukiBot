import os
import uuid
from typing import Tuple, Union, List

import nonebot
from PIL import Image, ImageFont, ImageDraw

default_color = (255, 255, 255, 255)
default_font = "resources/fonts/MiSans-Semibold.ttf"


def render_canvas_from_json(file: str, background: Image) -> "Canvas":
    pass


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
        self.canvas: Canvas | None = None
        self.uv_size = uv_size
        self.box_size = box_size
        self.parent_point = parent_point
        self.point = point
        self.parent: BasePanel | None = None
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
        self.draw_line_list = []

    def export(self, file, alpha=False):
        self.base_img = self.base_img.convert("RGBA")
        self.save_as((0, 0, 1, 1))
        draw = ImageDraw.Draw(self.base_img)
        for line in self.draw_line_list:
            draw.line(*line)
        if not alpha:
            self.base_img = self.base_img.convert("RGB")
        self.base_img.save(file)

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
        control_path = ""
        for i, seq in enumerate(path.split(".")):
            if seq not in sub_obj.__dict__:
                raise KeyError(f"在{control_path}中找不到控件：{seq}")
            control_path += f".{seq}"
            sub_obj = sub_obj.__dict__[seq]
        return sub_obj.actual_pos

    def get_actual_pixel_size(self, path: str) -> Union[None, Tuple[int, int]]:
        """
        获取控件实际像素长宽
        函数执行时间较长
        :param path: 控件路径
        :return:
        """
        sub_obj = self
        self.save_as((0, 0, 1, 1), True)
        control_path = ""
        for i, seq in enumerate(path.split(".")):
            if seq not in sub_obj.__dict__:
                raise KeyError(f"在{control_path}中找不到控件：{seq}")
            control_path += f".{seq}"
            sub_obj = sub_obj.__dict__[seq]
        dx = int(sub_obj.canvas.base_img.size[0] * (sub_obj.actual_pos[2] - sub_obj.actual_pos[0]))
        dy = int(sub_obj.canvas.base_img.size[1] * (sub_obj.actual_pos[3] - sub_obj.actual_pos[1]))
        return dx, dy

    def get_actual_pixel_box(self, path: str) -> Union[None, Tuple[int, int, int, int]]:
        """
        获取控件实际像素大小盒子
        函数执行时间较长
        :param path: 控件路径
        :return:
        """
        sub_obj = self
        self.save_as((0, 0, 1, 1), True)
        control_path = ""
        for i, seq in enumerate(path.split(".")):
            if seq not in sub_obj.__dict__:
                raise KeyError(f"在{control_path}中找不到控件：{seq}")
            control_path += f".{seq}"
            sub_obj = sub_obj.__dict__[seq]
        x1 = int(sub_obj.canvas.base_img.size[0] * sub_obj.actual_pos[0])
        y1 = int(sub_obj.canvas.base_img.size[1] * sub_obj.actual_pos[1])
        x2 = int(sub_obj.canvas.base_img.size[2] * sub_obj.actual_pos[2])
        y2 = int(sub_obj.canvas.base_img.size[3] * sub_obj.actual_pos[3])
        return x1, y1, x2, y2

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
        control_path = ""
        for i, seq in enumerate(path.split(".")):
            if seq not in sub_obj.__dict__:
                raise KeyError(f"在{control_path}中找不到控件：{seq}")
            control_path += f".{seq}"
            sub_obj = sub_obj.__dict__[seq]
        return sub_obj

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
        self.draw_line_list.append((xy_box, color, width))


class Panel(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point):
        super(Panel, self).__init__(uv_size, box_size, parent_point, point)


class TextSegment:
    def __init__(self, text, **kwargs):
        if not isinstance(text, str):
            raise TypeError("请输入字符串")
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
    def __init__(self, uv_size, box_size, parent_point, point, text: Union[str, list], font=default_font, color=(255, 255, 255, 255), vertical=False,
                 line_feed=False, force_size=False, fill=(0, 0, 0, 0), fillet=0, outline=(0, 0, 0, 0), outline_width=0, rectangle_side=0, font_size=None, dp: int = 5,
                 anchor: str = "la"):
        """
        :param uv_size:
        :param box_size:
        :param parent_point:
        :param point:
        :param text: list[TextSegment] | str
        :param font:
        :param color:
        :param vertical: 是否竖直
        :param line_feed: 是否换行
        :param force_size: 强制大小
        :param dp: 字体大小递减精度
        :param anchor : https://www.zhihu.com/question/474216280
        :param fill: 底部填充颜色
        :param fillet: 填充圆角
        :param rectangle_side: 边框宽度
        :param outline: 填充矩形边框颜色
        :param outline_width: 填充矩形边框宽度
        """
        self.actual_pos = None
        self.outline_width = outline_width
        self.outline = outline
        self.fill = fill
        self.fillet = fillet
        self.font = font
        self.text = text
        self.color = color
        self.force_size = force_size
        self.vertical = vertical
        self.line_feed = line_feed
        self.dp = dp
        self.font_size = font_size
        self.rectangle_side = rectangle_side
        self.anchor = anchor
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
                if self.fill[-1] > 0:
                    rectangle = Shape.rectangle(size=(actual_size[0] + 2 * self.rectangle_side, actual_size[1] + 2 * self.rectangle_side), fillet=self.fillet, fill=self.fill,
                                                width=self.outline_width, outline=self.outline)
                    self.canvas.base_img.paste(im=rectangle, box=(start_point[0] - self.rectangle_side,
                                                                  start_point[1] - self.rectangle_side,
                                                                  start_point[0] + actual_size[0] + self.rectangle_side,
                                                                  start_point[1] + actual_size[1] + self.rectangle_side),
                                               mask=rectangle.split()[-1])
                draw.text((start_point[0] - self.rectangle_side, start_point[1] - self.rectangle_side),
                          text_segment.text, text_segment.color, font=image_font, anchor=self.anchor)
                text_width = image_font.getsize(text_segment.text)
                start_point[0] += text_width[0]


class Img(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point, img: Image.Image, keep_ratio=True):
        self.img_base_img = img
        self.keep_ratio = keep_ratio
        super(Img, self).__init__(uv_size, box_size, parent_point, point)

    def load(self, only_calculate=False):
        self.preprocess()
        self.img_base_img = self.img_base_img.convert("RGBA")
        limited_size = int((self.canvas_box[2] - self.canvas_box[0]) * self.canvas.base_img.size[0]), \
            int((self.canvas_box[3] - self.canvas_box[1]) * self.canvas.base_img.size[1])

        if self.keep_ratio:
            """保持比例"""
            actual_ratio = self.img_base_img.size[0] / self.img_base_img.size[1]
            limited_ratio = limited_size[0] / limited_size[1]
            if actual_ratio >= limited_ratio:
                # 图片过长
                self.img_base_img = self.img_base_img.resize(
                    (int(self.img_base_img.size[0] * limited_size[0] / self.img_base_img.size[0]),
                     int(self.img_base_img.size[1] * limited_size[0] / self.img_base_img.size[0]))
                )
            else:
                self.img_base_img = self.img_base_img.resize(
                    (int(self.img_base_img.size[0] * limited_size[1] / self.img_base_img.size[1]),
                     int(self.img_base_img.size[1] * limited_size[1] / self.img_base_img.size[1]))
                )

        else:
            """不保持比例"""
            self.img_base_img = self.img_base_img.resize(limited_size)

        # 占比长度
        if isinstance(self.parent, Img) or isinstance(self.parent, Text):
            self.parent.canvas_box = self.parent.actual_pos

        dx0 = self.parent.canvas_box[2] - self.parent.canvas_box[0]
        dy0 = self.parent.canvas_box[3] - self.parent.canvas_box[1]

        dx1 = self.img_base_img.size[0] / self.canvas.base_img.size[0]
        dy1 = self.img_base_img.size[1] / self.canvas.base_img.size[1]
        start_point = (
            int((self.parent.canvas_box[0] + dx0 * self.parent_point[0] - dx1 * self.point[0]) * self.canvas.base_img.size[0]),
            int((self.parent.canvas_box[1] + dy0 * self.parent_point[1] - dy1 * self.point[1]) * self.canvas.base_img.size[1])
        )
        alpha = self.img_base_img.split()[3]
        self.actual_pos = (
            start_point[0] / self.canvas.base_img.size[0],
            start_point[1] / self.canvas.base_img.size[1],
            (start_point[0] + self.img_base_img.size[0]) / self.canvas.base_img.size[0],
            (start_point[1] + self.img_base_img.size[1]) / self.canvas.base_img.size[1],
        )
        if not only_calculate:
            self.canvas.base_img.paste(self.img_base_img, start_point, alpha)

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
        if not self.keep_ratio and self.img_base_img is not None and self.img_base_img.size[0] / self.img_base_img.size[1] != limited_size[0] / limited_size[1]:
            self.img_base_img = self.img_base_img.resize(limited_size)
        self.img_base_img = Shape.rectangle(size=limited_size, fillet=self.fillet, fill=self.color, width=self.outline_width, outline=self.outline_color)


class Color:
    GREY = (128, 128, 128, 255)
    RED = (255, 0, 0, 255)
    GREEN = (0, 255, 0, 255)
    BLUE = (0, 0, 255, 255)
    YELLOW = (255, 255, 0, 255)
    PURPLE = (255, 0, 255, 255)
    CYAN = (0, 255, 255, 255)
    WHITE = (255, 255, 255, 255)
    BLACK = (0, 0, 0, 255)

    @staticmethod
    def hex2dec(colorHex: str) -> Tuple[int, int, int, int]:
        """
        :param colorHex: FFFFFFFF （ARGB）-> (R, G, B, A)
        :return:
        """
        return int(colorHex[2:4], 16), int(colorHex[4:6], 16), int(colorHex[6:8], 16), int(colorHex[0:2], 16)


class Shape:
    @staticmethod
    def circular(radius: int, fill: tuple, width: int = 0, outline: tuple = Color.BLACK) -> Image.Image:
        """
        :param radius: 半径（像素）
        :param fill: 填充颜色
        :param width: 轮廓粗细（像素）
        :param outline: 轮廓颜色
        :return: 圆形Image对象
        """
        img = Image.new("RGBA", (radius * 2, radius * 2), color=radius)
        draw = ImageDraw.Draw(img)
        draw.ellipse(xy=(0, 0, radius * 2, radius * 2), fill=fill, outline=outline, width=width)
        return img

    @staticmethod
    def rectangle(size: Tuple[int, int], fill: tuple, width: int = 0, outline: tuple = Color.BLACK, fillet: int = 0) -> Image.Image:
        """
        :param fillet: 圆角半径（像素）
        :param size: 长宽（像素）
        :param fill: 填充颜色
        :param width: 轮廓粗细（像素）
        :param outline: 轮廓颜色
        :return: 矩形Image对象
        """
        img = Image.new("RGBA", size, color=fill)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(xy=(0, 0, size[0], size[1]), fill=fill, outline=outline, width=width, radius=fillet)
        return img

    @staticmethod
    def ellipse(size: Tuple[int, int], fill: tuple, outline: int = 0, outline_color: tuple = Color.BLACK) -> Image.Image:
        """
        :param size: 长宽（像素）
        :param fill: 填充颜色
        :param outline: 轮廓粗细（像素）
        :param outline_color: 轮廓颜色
        :return: 椭圆Image对象
        """
        img = Image.new("RGBA", size, color=fill)
        draw = ImageDraw.Draw(img)
        draw.ellipse(xy=(0, 0, size[0], size[1]), fill=fill, outline=outline_color, width=outline)
        return img

    @staticmethod
    def polygon(points: List[Tuple[int, int]], fill: tuple, outline: int, outline_color: tuple) -> Image.Image:
        """
        :param points: 多边形顶点列表
        :param fill: 填充颜色
        :param outline: 轮廓粗细（像素）
        :param outline_color: 轮廓颜色
        :return: 多边形Image对象
        """
        img = Image.new("RGBA", (max(points)[0], max(points)[1]), color=fill)
        draw = ImageDraw.Draw(img)
        draw.polygon(xy=points, fill=fill, outline=outline_color, width=outline)
        return img

    @staticmethod
    def line(points: List[Tuple[int, int]], fill: tuple, width: int) -> Image:
        """
        :param points: 线段顶点列表
        :param fill: 填充颜色
        :param width: 线段粗细（像素）
        :return: 线段Image对象
        """
        img = Image.new("RGBA", (max(points)[0], max(points)[1]), color=fill)
        draw = ImageDraw.Draw(img)
        draw.line(xy=points, fill=fill, width=width)
        return img


class Utils:

    @staticmethod
    def central_clip_by_ratio(img: Image.Image, size: Tuple, use_cache=True):
        """
        :param use_cache: 是否使用缓存，剪切过一次后默认生成缓存
        :param img:
        :param size: 仅为比例，满填充裁剪
        :return:
        """
        cache_file_path = str()
        if use_cache:
            filename_without_end = ".".join(os.path.basename(img.fp.name).split(".")[0:-1]) + f"_{size[0]}x{size[1]}" + ".png"
            cache_file_path = os.path.join(".cache", filename_without_end)
            if os.path.exists(cache_file_path):
                nonebot.logger.info("本次使用缓存加载图片，不裁剪")
                return Image.open(os.path.join(".cache", filename_without_end))
        img_ratio = img.size[0] / img.size[1]
        limited_ratio = size[0] / size[1]
        if limited_ratio > img_ratio:
            actual_size = (
                img.size[0],
                img.size[0] / size[0] * size[1]
            )
            box = (
                0, (img.size[1] - actual_size[1]) // 2,
                img.size[0], img.size[1] - (img.size[1] - actual_size[1]) // 2
            )
        else:
            actual_size = (
                img.size[1] / size[1] * size[0],
                img.size[1],
            )
            box = (
                (img.size[0] - actual_size[0]) // 2, 0,
                img.size[0] - (img.size[0] - actual_size[0]) // 2, img.size[1]
            )
        img = img.crop(box).resize(size)
        if use_cache:
            img.save(cache_file_path)
        return img

    @staticmethod
    def circular_clip(img: Image.Image):
        """
        裁剪为alpha圆形

        :param img:
        :return:
        """
        length = min(img.size)
        alpha_cover = Image.new("RGBA", (length, length), color=(0, 0, 0, 0))
        if img.size[0] > img.size[1]:
            box = (
                (img.size[0] - img[1]) // 2, 0,
                (img.size[0] - img[1]) // 2 + img.size[1], img.size[1]
            )
        else:
            box = (
                0, (img.size[1] - img.size[0]) // 2,
                img.size[0], (img.size[1] - img.size[0]) // 2 + img.size[0]
            )
        img = img.crop(box).resize((length, length))
        draw = ImageDraw.Draw(alpha_cover)
        draw.ellipse(xy=(0, 0, length, length), fill=(255, 255, 255, 255))
        alpha = alpha_cover.split()[-1]
        img.putalpha(alpha)
        return img

    @staticmethod
    def open_img(path) -> Image.Image:
        return Image.open(path, "RGBA")
