import os
import uuid
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

    def get_actual_size(self, path: str) -> Union[None, Tuple[float, float, float, float]]:
        """
        获取控件实际大小
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

    def get_parent_size(self, path: str) -> Union[None, Tuple[float, float, float, float]]:
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

    def get_control_by_path(self, path: str):
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
        ac_pos = self.get_actual_size(path)
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


class Text(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point, text, font, color=(255, 255, 255, 255), vertical=False, line_feed=False, force_size=False, dp: int = 5):
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

    def load(self, only_calculate=False):
        """限制区域像素大小"""
        limited_size = int((self.canvas_box[2] - self.canvas_box[0]) * self.canvas.base_img.size[0]), int((self.canvas_box[3] - self.canvas_box[1]) * self.canvas.base_img.size[1])
        font_size = limited_size[1]
        image_font = ImageFont.truetype(self.font, font_size)
        actual_size = image_font.getsize(self.text)
        while (actual_size[0] > limited_size[0] or actual_size[1] > limited_size[1]) and not self.force_size:
            font_size -= self.dp
            image_font = ImageFont.truetype(self.font, font_size)
            actual_size = image_font.getsize(self.text)
        draw = ImageDraw.Draw(self.canvas.base_img)
        if isinstance(self.parent, Img) or isinstance(self.parent, Text):
            self.parent.canvas_box = self.parent.actual_pos
        dx0 = self.parent.canvas_box[2] - self.parent.canvas_box[0]
        dy0 = self.parent.canvas_box[3] - self.parent.canvas_box[1]
        dx1 = actual_size[0] / self.canvas.base_img.size[0]
        dy1 = actual_size[1] / self.canvas.base_img.size[1]
        start_point = (
            int((self.parent.canvas_box[0] + dx0 * self.parent_point[0] - dx1 * self.point[0]) * self.canvas.base_img.size[0]),
            int((self.parent.canvas_box[1] + dy0 * self.parent_point[1] - dy1 * self.point[1]) * self.canvas.base_img.size[1])
        )
        self.actual_pos = (
            start_point[0] / self.canvas.base_img.size[0],
            start_point[1] / self.canvas.base_img.size[1],
            (start_point[0] + actual_size[0]) / self.canvas.base_img.size[0],
            (start_point[1] + actual_size[1]) / self.canvas.base_img.size[1],
        )
        if not only_calculate:
            draw.text(start_point, self.text, self.color, font=image_font)


class Img(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point, img: Image.Image, keep_ratio=True):
        self.img = img
        self.keep_ratio = keep_ratio
        super(Img, self).__init__(uv_size, box_size, parent_point, point)

    def load(self, only_calculate=False):
        self.img = self.img.convert("RGBA")
        limited_size = int((self.canvas_box[2] - self.canvas_box[0]) * self.canvas.base_img.size[0]), int((self.canvas_box[3] - self.canvas_box[1]) * self.canvas.base_img.size[1])

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
            """保持比例"""
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
