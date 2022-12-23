from typing import Tuple, Union, List
from PIL import Image


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
        self.children: List["BasePanel"] = []

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
        for child in self.children:
            # 此节点在画布上的盒子
            if self is Canvas:
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
            child.parent = self
            child.load(child_canvas_box)
            child.save_as(child_canvas_box)


class Canvas(BasePanel):
    def __init__(self, base_img: Image.Image):
        super(Canvas, self).__init__()


class Panel(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point):
        super(Panel, self).__init__(uv_size, box_size, parent_point, point)


class Text(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point, text):
        super(Text, self).__init__(uv_size, box_size, parent_point, point)

    def load(self, canvas_box):
        pass


class Img(BasePanel):
    def __init__(self, uv_size, box_size, parent_point, point, img: Image.Image):
        super(Img, self).__init__(uv_size, box_size, parent_point, point)
