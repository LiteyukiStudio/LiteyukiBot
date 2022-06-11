from PIL import Image, ImageFont, ImageDraw
from typing import Tuple, Union, List


class Canvas:
    def __init__(self, base_img: Image.Image = Image.new(mode="RGBA", size=(1920, 1080), color=0)):
        self.base_img: Image.Image = base_img

    @property
    def size(self) -> Tuple[int, int]:
        """画布实际像素大小"""
        return self.base_img.size

    def save(self) -> str:
        return str(self.base_img.size)

    def generate(self):
        self.set_parent()

    def set_parent(self):
        for value in tuple(self.__dict__.values()):
            if isinstance(value, BaseNode):
                value: BaseNode
                value.parent = self
                value.set_parent()
                value.place()


class BaseNode:
    def __init__(self,
                 size: Tuple[float, float],
                 parent_ap: Tuple[float, float],
                 ap: Tuple[float, float]
                 ):
        """
        :param size: 相对于父节点百分比小数
        :param parent_ap: 父节点锚点[0-1, 0-1]
        :param ap: 节点锚点[0-1, 0-1]
        """
        self.parent: Union["Canvas", "BaseNode", None] = None
        self.size: Tuple[float, float] = size
        self.parent_ap: Tuple[float, float] = parent_ap
        self.ap: Tuple[float, float] = ap
        self.child: List["BaseNode"] = []

    @property
    def canvas(self) -> "Canvas":
        """
        :return: 获取顶级画布对象
        """
        if isinstance(self.parent, Canvas):
            return self.parent
        else:
            return self.parent.canvas

    @property
    def parent_uv(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """获取子节点在父节点上的相对uv两点坐标"""
        return (self.parent_ap[0] - self.size[0] * self.ap[0], self.parent_ap[1] - self.size[1] * self.ap[1]), \
               (self.parent_ap[0] + self.size[0] * (1 - self.ap[0]), self.parent_ap[1] + self.size[1] * (1 - self.ap[1]))

    @property
    def canvas_uv(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """节点在顶级canvas上的uv两点坐标"""
        if isinstance(self.parent, Canvas):
            return self.parent_uv
        else:
            parent_parent_uv = self.parent.canvas_uv
            parent_uv = self.canvas_uv
            dw, dh = parent_parent_uv[1][0] - parent_parent_uv[0][0], parent_parent_uv[1][1] - parent_parent_uv[0][1]
            return (parent_parent_uv[0][0] + parent_uv[0][0] * dw, parent_parent_uv[0][1] + parent_uv[0][1] * dh), \
                   (parent_parent_uv[0][0] + parent_uv[1][0] * dw, parent_parent_uv[0][1] + parent_uv[1][1] * dh)

    @property
    def canvas_uv_size(self) -> Tuple[float, float]:
        return self.canvas_uv[1][0] - self.canvas_uv[0][0], self.canvas_uv[1][1] - self.canvas_uv[0][1]

    @property
    def canvas_pos(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        画布uv实际像素点的两点坐标

        :return:
        """
        return (int(self.canvas.size[0] * self.canvas_uv[0][0]), int(self.canvas.size[1] * self.canvas_uv[0][1])), \
               (int(self.canvas.size[0] * self.canvas_uv[1][0]), int(self.canvas.size[1] * self.canvas_uv[1][1]))

    @property
    def canvas_pos_size(self) -> Tuple[int, int]:
        return self.canvas_pos[1][0] - self.canvas_pos[0][0], \
               self.canvas_pos[1][1] - self.canvas_pos[0][1]

    @property
    def canvas_ap_pos(self) -> Tuple[int, int]:
        """节点的矩形几何中心在顶级canvas的像素坐标点"""
        return int((self.canvas_uv[0][0] + self.canvas_uv[1][0]) / 2 * self.canvas.size[0]), int((self.canvas_uv[0][1] + self.canvas_uv[1][1]) / 2 * self.canvas.size[1])

    def set_parent(self):
        for value in tuple(self.__dict__.values()):
            if isinstance(value, BaseNode):
                value.parent = self
                value.set_parent()
                value.place()

    def place(self):
        """
        将子对象放置到画布上
        此方法由父级节点生成时调用

        :return:
        """
        pass


class PanelNode(BaseNode):
    def __init__(self,
                 size: Tuple[float, float],
                 parent_ap: Tuple[float, float],
                 ap: Tuple[float, float]
                 ):
        """
        用于划分区域，实际不显示

        :param size: 百分比大小
        :param parent_ap: 父锚点
        :param ap: 子锚点
        """
        super().__init__(size, parent_ap, ap)


class TextNode(BaseNode):
    def __init__(self,
                 size: Tuple[float, float],
                 parent_ap: Tuple[float, float],
                 ap: Tuple[float, float],
                 text: str,
                 font: str,
                 align: str = "CC",
                 color: Union[str, Tuple[int, int, int, int]] = None,
                 limit: bool = True
                 ):
        """
        :param align: LU,CC,RD不区分大小，
        :param text: 文本内容
        :param size: 百分比大小
        :param parent_ap: 父锚点
        :param ap: 子锚点
        :param limit: 限制大小在区域内
        """
        super().__init__(size, parent_ap, ap)
        self.color = color
        self.font_path = font
        self.text: str = text
        self.limit = limit
        x_align, y_align = tuple(align)
        if x_align.upper() not in ["L", "C", "R"] or y_align.upper() not in ["U", "C", "D"]:
            raise ValueError("'%s%s' 不是一个合法的对齐参数" % (x_align, y_align))
        self.x_align = x_align.upper()
        self.y_align = y_align.upper()

        self.scale = 0.95

    def place(self):
        # 限制像素大小
        limited_width, limited_height = self.canvas_pos_size
        # 字体初次像素大小
        font_size = int(limited_width / len(self.text.splitlines()))
        # 初次字体实例化
        font = ImageFont.truetype(self.font_path, size=font_size)
        # 初次文本大小
        init_size = font.getsize(text=self.text)
        while init_size[0] > limited_width or init_size[1] > limited_height:
            # 减小
            font_size *= self.scale
            font = ImageFont.truetype(self.font_path, size=int(font_size))
            init_size = font.getsize(text=self.text)
        # 创建绘画对象
        actual_width, actual_height = font.getsize(text=self.text)
        draw = ImageDraw.Draw(self.canvas.base_img)

        if self.x_align == "L":
            x = self.canvas_pos[0][0]
        elif self.x_align == "R":
            x = self.canvas_pos[1][0] - actual_width
        else:
            x = self.canvas_ap_pos[0] - actual_width // 2

        if self.y_align == "U":
            y = self.canvas_pos[0][1]
        elif self.y_align == "D":
            y = self.canvas_pos[1][1] - actual_height
        else:
            y = self.canvas_ap_pos[1] - actual_height // 2

        draw.text(xy=(x, y), text=self.text, fill=self.color, font=font)


class ImgNode(BaseNode):
    def __init__(self,
                 img: str,
                 size: Tuple[float, float],
                 parent_ap: Tuple[float, float],
                 ap: Tuple[float, float],
                 limit: bool = True,
                 resize: bool = True
                 ):
        """
        :param img: 图片对象
        :param limit: 是否限制图片大小
        :param resize: 是否拉伸限制，仅在limit为True时生效
        """
        super().__init__(size, parent_ap, ap)
        self.img: Image.Image = img


c = Canvas()
c.Title = TextNode("你好", (0.5, 0.2), (0.5, 0.5), (0.5, 0.5), font="")
c.generate()
c.base_img.show()
