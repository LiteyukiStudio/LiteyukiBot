from __future__ import annotations

import os
import uuid
from PIL import Image, ImageFont, ImageDraw
from .base import ExConfig
from typing import Tuple
from nonebot.utils import run_sync


class Cardimage:
    """
    UI卡片生成类
    """

    def __init__(self, baseImg: Image.Image):
        fileName = "%s.png" % uuid.uuid4()
        self.fp = os.path.join(ExConfig.cache_path, fileName)
        self.baseImg = baseImg

    @run_sync
    def addText(self, uvSize: Tuple[float, float], boxSize: Tuple[float, float],
                xyOffset: Tuple[float, float],
                baseAnchor: Tuple[float, float],
                textAnchor: Tuple[float, float], content: str, font: str = os.path.join(ExConfig.res_path, "fonts/MiSans-Medium.ttf"),
                color: Tuple[int, int, int, int] = (255, 255, 255, 255), sizePercent: float = 1, force_size=False):
        """
        :param force_size: 强制大小
        :param sizePercent: 大小百分比,默认1
        :param baseAnchor: 基底锚点[0-1, 0-1]
        :param textAnchor: 子对象锚点[0-1, 0-1]
        :param color: 颜色四维向量,默认全黑
        :param xyOffset: UV偏移量, 基于uvSize
        :param uvSize: UV分数
        :param boxSize: 对象大小, 基于uvSize
        :param content: words content
        :param font: font path
        :return: 基于uv size的左上右下点位

        在限制区域添加单行文本
        """
        limitedSize = int(boxSize[0] / uvSize[0] * self.baseImg.size[0]), int(
            boxSize[1] / uvSize[1] * self.baseImg.size[1])
        initWidth, initHeight = limitedSize
        imageFont = ImageFont.truetype(font, size=initHeight)
        actualSize = imageFont.getsize(content)
        while (actualSize[0] > limitedSize[0] or actualSize[1] > limitedSize[1]) and not force_size:
            initHeight -= 5
            imageFont = ImageFont.truetype(font, size=initHeight)
            actualSize = imageFont.getsize(content)
        draw = ImageDraw.Draw(self.baseImg)
        imageFont = ImageFont.truetype(font, size=initHeight * sizePercent)
        # 基类锚点绝对位置int
        baseAnchorXY = int(self.baseImg.size[0] * (baseAnchor[0] + xyOffset[0] / uvSize[0])), int(
            self.baseImg.size[1] * (baseAnchor[1] + xyOffset[1] / uvSize[1]))

        # 子对象锚点偏移量float|int
        textAnchorXY = int(actualSize[0] * textAnchor[0]), int(actualSize[1] * textAnchor[1])

        actualPos = baseAnchorXY[0] - textAnchorXY[0], baseAnchorXY[1] - textAnchorXY[1]

        draw.text(xy=actualPos, text=content, fill=color, font=imageFont)
        return actualPos[0] / self.baseImg.size[0] * uvSize[0], actualPos[1] / self.baseImg.size[1] * uvSize[1], (
                actualPos[0] + actualSize[0]) / self.baseImg.size[0] * uvSize[0], (actualPos[1] + actualSize[1]) / \
               self.baseImg.size[1] * uvSize[1]

    @run_sync
    def addImage(self, uvSize: Tuple[float, float], boxSize: Tuple[float, float],
                 xyOffset: Tuple[float, float],
                 baseAnchor: Tuple[float, float],
                 imgAnchor: Tuple[float, float], img: Image.Image,
                 sizePercent: float = 1):
        """
        :param img: 图片对象
        :param sizePercent: 大小百分比,默认1
        :param baseAnchor: 基底锚点[0-1, 0-1]
        :param imgAnchor: 子对象锚点[0-1, 0-1]
        :param xyOffset: UV偏移量, 基于uvSize
        :param uvSize: UV分数
        :param boxSize: 对象大小, 基于uvSize
        :return:

        在限制区域添加图片
        """
        # 绝对像素限制
        limitedSize = int(boxSize[0] / uvSize[0] * self.baseImg.size[0]), int(
            boxSize[1] / uvSize[1] * self.baseImg.size[1])
        limitedRatio = limitedSize[0] / limitedSize[1]
        actualRatio = img.size[0] / img.size[1]
        if actualRatio > limitedRatio:
            # 宽度过宽
            img = img.resize(size=(int(limitedSize[0] / img.size[0] * img.size[0] * sizePercent),
                                   int(limitedSize[0] / img.size[0] * img.size[1] * sizePercent)),
                             resample=Image.ANTIALIAS)
        else:
            img = img.resize(size=(int(limitedSize[1] / img.size[1] * img.size[0] * sizePercent),
                                   int(limitedSize[1] / img.size[1] * img.size[1] * sizePercent)),
                             resample=Image.ANTIALIAS)
        actualSize = img.size

        # 基类锚点绝对位置int
        baseAnchorXY = int(self.baseImg.size[0] * (baseAnchor[0] + xyOffset[0] / uvSize[0])), int(
            self.baseImg.size[1] * (baseAnchor[1] + xyOffset[1] / uvSize[1]))

        # 子对象锚点偏移量float|int
        textAnchorXY = int(actualSize[0] * imgAnchor[0]), int(actualSize[1] * imgAnchor[1])

        actualPos = baseAnchorXY[0] - textAnchorXY[0], baseAnchorXY[1] - textAnchorXY[1]
        alpha = img.split()[3]
        self.baseImg.paste(img, box=actualPos, mask=alpha)
        return actualPos[0] / self.baseImg.size[0] * uvSize[0], actualPos[1] / self.baseImg.size[1] * uvSize[1], (
                actualPos[0] + actualSize[0]) / self.baseImg.size[0] * uvSize[0], (actualPos[1] + actualSize[1]) / \
               self.baseImg.size[1] * uvSize[1]

    @run_sync
    def drawLine(self, uvSize: Tuple[float, float], p1: Tuple[float, float], p2: Tuple[float, float], color: Tuple[int, int, int, int] = (255, 255, 255, 255), width: int = 1):
        """
        :param uvSize: 基图大小
        :param p1: 基于uv的1点位
        :param p2: 基于uv的2点位
        :param color: 颜色
        :param width: 宽度
        :return:
        """
        xy_int = (int(p1[0] / uvSize[0] * self.baseImg.size[0]), int(p1[1] / uvSize[1] * self.baseImg.size[1]), int(p2[0] / uvSize[0] * self.baseImg.size[0]),
                  int(p2[1] / uvSize[1] * self.baseImg.size[1]))
        draw = ImageDraw.Draw(self.baseImg)
        draw.line(xy=xy_int, fill=color, width=width)

    @run_sync
    def save(self, fp):
        self.baseImg.save(fp)

    async def getPath(self) -> str:
        """
        :return:
        缓存并返回文件路径
        """

        await self.save(self.fp)
        return self.fp.replace("\\", "/")

    async def delete(self):
        """
        :return:

        删除缓存
        """
        os.remove(self.fp)

    @staticmethod
    def hex2dec(colorHex: str) -> Tuple[int, int, int, int]:
        """
        :param colorHex: FFFFFFFF （ARGB）-> (R, G, B, A)
        :return:
        """
        return int(colorHex[2:4], 16), int(colorHex[4:6], 16), int(colorHex[6:8], 16), int(colorHex[0:2], 16)

