import json
from typing import List, Any

from PIL import Image
from arclet.alconna import Alconna
from nb_cli import run_sync
from nonebot import on_command
from nonebot_plugin_alconna import on_alconna, Alconna, Subcommand, Args, MultiVar, Arparma, UniMessage
from pydantic import BaseModel

from .canvas import *
from ...utils.base.resource import get_path

resolution = 256


class Entrance(BaseModel):
    identifier: str
    size: tuple[int, int]
    dest: List[str]


class Station(BaseModel):
    identifier: str
    chineseName: str
    englishName: str
    position: tuple[int, int]


class Line(BaseModel):
    identifier: str
    chineseName: str
    englishName: str
    color: Any
    stations: List["Station"]


font_light = get_path("templates/fonts/MiSans/MiSans-Light.woff2")
font_bold = get_path("templates/fonts/MiSans/MiSans-Bold.woff2")

@run_sync
def generate_entrance_sign(name: str, aliases: List[str], lineInfo: List[Line], entranceIdentifier: str, ratio: tuple[int | float, int | float],
                           reso: int = resolution):
    """
    Generates an entrance sign for the ride.
    """
    width, height = ratio[0] * reso, ratio[1] * reso
    baseCanvas = Canvas(Image.new("RGBA", (width, height), Color.WHITE))
    # 加黑色图框
    baseCanvas.outline = Img(
        uv_size=(1, 1),
        box_size=(1, 1),
        parent_point=(0, 0),
        point=(0, 0),
        img=Shape.rectangle(
            size=(width, height),
            fillet=0,
            fill=(0, 0, 0, 0),
            width=15,
            outline=Color.BLACK
        )
    )

    baseCanvas.contentPanel = Panel(
        uv_size=(width, height),
        box_size=(width - 28, height - 28),
        parent_point=(0.5, 0.5),
        point=(0.5, 0.5),
    )

    linePanelHeight = 0.7 * ratio[1]
    linePanelWidth = linePanelHeight * 1.3

    # 画线路面板部分

    for i, line in enumerate(lineInfo):
        linePanel = baseCanvas.contentPanel.__dict__[f"Line_{i}_Panel"] = Panel(
            uv_size=ratio,
            box_size=(linePanelWidth, linePanelHeight),
            parent_point=(i * linePanelWidth / ratio[0], 1),
            point=(0, 1),
        )

        linePanel.colorCube = Img(
            uv_size=(1, 1),
            box_size=(0.15, 1),
            parent_point=(0.125, 1),
            point=(0, 1),
            img=Shape.rectangle(
                size=(100, 100),
                fillet=0,
                fill=line.color,
            ),
            keep_ratio=False
        )

        textPanel = linePanel.TextPanel = Panel(
            uv_size=(1, 1),
            box_size=(0.625, 1),
            parent_point=(1, 1),
            point=(1, 1)
        )

        # 中文线路名
        textPanel.namePanel = Panel(
            uv_size=(1, 1),
            box_size=(1, 2 / 3),
            parent_point=(0, 0),
            point=(0, 0),
        )
        nameSize = baseCanvas.get_actual_pixel_size("contentPanel.Line_{}_Panel.TextPanel.namePanel".format(i))
        textPanel.namePanel.text = Text(
            uv_size=(1, 1),
            box_size=(1, 1),
            parent_point=(0.5, 0.5),
            point=(0.5, 0.5),
            text=line.chineseName,
            color=Color.BLACK,
            font_size=int(nameSize[1] * 0.5),
            force_size=True,
            font=font_bold

        )

        # 英文线路名
        textPanel.englishNamePanel = Panel(
            uv_size=(1, 1),
            box_size=(1, 1 / 3),
            parent_point=(0, 1),
            point=(0, 1),
        )
        englishNameSize = baseCanvas.get_actual_pixel_size("contentPanel.Line_{}_Panel.TextPanel.englishNamePanel".format(i))
        textPanel.englishNamePanel.text = Text(
            uv_size=(1, 1),
            box_size=(1, 1),
            parent_point=(0.5, 0.5),
            point=(0.5, 0.5),
            text=line.englishName,
            color=Color.BLACK,
            font_size=int(englishNameSize[1] * 0.6),
            force_size=True,
            font=font_light
        )

    # 画名称部分
    namePanel = baseCanvas.contentPanel.namePanel = Panel(
        uv_size=(1, 1),
        box_size=(1, 0.4),
        parent_point=(0.5, 0),
        point=(0.5, 0),
    )

    namePanel.text = Text(
        uv_size=(1, 1),
        box_size=(1, 1),
        parent_point=(0.5, 0.5),
        point=(0.5, 0.5),
        text=name,
        color=Color.BLACK,
        font_size=int(height * 0.3),
        force_size=True,
        font=font_bold
    )

    aliasesPanel = baseCanvas.contentPanel.aliasesPanel = Panel(
        uv_size=(1, 1),
        box_size=(1, 0.5),
        parent_point=(0.5, 1),
        point=(0.5, 1),

    )
    for j, alias in enumerate(aliases):
        aliasesPanel.__dict__[alias] = Text(
            uv_size=(1, 1),
            box_size=(0.35, 0.5),
            parent_point=(0.5, 0.5 * j),
            point=(0.5, 0),
            text=alias,
            color=Color.BLACK,
            font_size=int(height * 0.15),
            font=font_light
        )

    # 画入口标识
    entrancePanel = baseCanvas.contentPanel.entrancePanel = Panel(
        uv_size=(1, 1),
        box_size=(0.2, 1),
        parent_point=(1, 0.5),
        point=(1, 0.5),
    )
    # 中文文本
    entrancePanel.namePanel = Panel(
        uv_size=(1, 1),
        box_size=(1, 0.5),
        parent_point=(1, 0),
        point=(1, 0),
    )
    entrancePanel.namePanel.text = Text(
        uv_size=(1, 1),
        box_size=(1, 1),
        parent_point=(0, 0.5),
        point=(0, 0.5),
        text=f"{entranceIdentifier}出入口",
        color=Color.BLACK,
        font_size=int(height * 0.2),
        force_size=True,
        font=font_bold
    )
    # 英文文本
    entrancePanel.englishNamePanel = Panel(
        uv_size=(1, 1),
        box_size=(1, 0.5),
        parent_point=(1, 1),
        point=(1, 1),
    )
    entrancePanel.englishNamePanel.text = Text(
        uv_size=(1, 1),
        box_size=(1, 1),
        parent_point=(0, 0.5),
        point=(0, 0.5),
        text=f"Entrance {entranceIdentifier}",
        color=Color.BLACK,
        font_size=int(height * 0.15),
        force_size=True,
        font=font_light
    )

    return baseCanvas.base_img.tobytes()


crt_alc = on_alconna(
    Alconna(
        "crt",
        Subcommand(
            "entrance",
            Args["name", str]["lines", str, ""]["entrance", int, 1],  # /crt entrance 璧山&Bishan 1号线&Line1&#ff0000,27号线&Line1&#ff0000 1A
        )
    )
)


@crt_alc.assign("entrance")
async def _(result: Arparma):
    args = result.subcommands.get("entrance").args
    name = args["name"]
    lines = args["lines"]
    entrance = args["entrance"]
    line_info = []
    for line in lines.split(","):
        line_args = line.split("&")
        line_info.append(Line(
            identifier=1,
            chineseName=line_args[0],
            englishName=line_args[1],
            color=line_args[2],
            stations=[]
        ))
    img_bytes = await generate_entrance_sign(
        name=name,
        aliases=name.split("&"),
        lineInfo=line_info,
        entranceIdentifier=entrance,
        ratio=(8, 1),
        reso=256,
    )
    await crt_alc.finish(
        UniMessage.image(raw=img_bytes)
    )


def generate_platform_line_pic(line: Line, station: Station, ratio=None, reso: int = resolution):
    """
    生成站台线路图
    :param line: 线路对象
    :param station: 本站点对象
    :param ratio: 比例
    :param reso: 分辨率，1：reso
    :return: 两个方向的站牌
    """
    if ratio is None:
        ratio = [4, 1]
    width, height = ratio[0] * reso, ratio[1] * reso
    baseCanvas = Canvas(Image.new("RGBA", (width, height), Color.YELLOW))
    # 加黑色图框
    baseCanvas.linePanel = Panel(
        uv_size=(1, 1),
        box_size=(0.8, 0.15),
        parent_point=(0.5, 0.5),
        point=(0.5, 0.5),
    )

    # 直线块
    baseCanvas.linePanel.recLine = Img(
        uv_size=(1, 1),
        box_size=(1, 1),
        parent_point=(0.5, 0.5),
        point=(0.5, 0.5),
        img=Shape.rectangle(
            size=(10, 10),
            fill=line.color,
        ),
        keep_ratio=False
    )
    # 灰色直线块
    baseCanvas.linePanel.recLineGrey = Img(
        uv_size=(1, 1),
        box_size=(1, 1),
        parent_point=(0.5, 0.5),
        point=(0.5, 0.5),
        img=Shape.rectangle(
            size=(10, 10),
            fill=Color.GREY,
        ),
        keep_ratio=False
    )
    # 生成各站圆点
    outline_width = 40
    circleForward = Shape.circular(
        radius=200,
        fill=Color.WHITE,
        width=outline_width,
        outline=line.color,
    )

    circleThisPanel = Canvas(Image.new("RGBA", (200, 200), (0, 0, 0, 0)))
    circleThisPanel.circleOuter = Img(
        uv_size=(1, 1),
        box_size=(1, 1),
        parent_point=(0.5, 0.5),
        point=(0.5, 0.5),
        img=Shape.circular(
            radius=200,
            fill=Color.WHITE,
            width=outline_width,
            outline=line.color,
        ),
    )
    circleThisPanel.circleOuter.circleInner = Img(
        uv_size=(1, 1),
        box_size=(0.7, 0.7),
        parent_point=(0.5, 0.5),
        point=(0.5, 0.5),
        img=Shape.circular(
            radius=200,
            fill=line.color,
            width=0,
            outline=line.color,
        ),
    )

    circleThisPanel.export("a.png", alpha=True)
    circleThis = circleThisPanel.base_img

    circlePassed = Shape.circular(
        radius=200,
        fill=Color.WHITE,
        width=outline_width,
        outline=Color.GREY,
    )

    arrival = False
    distance = 1 / (len(line.stations) - 1)
    for i, sta in enumerate(line.stations):
        box_size = (1.618, 1.618)
        if sta.identifier == station.identifier:
            arrival = True
            baseCanvas.linePanel.recLine.__dict__["station_{}".format(sta.identifier)] = Img(
                uv_size=(1, 1),
                box_size=(1.8, 1.8),
                parent_point=(distance * i, 0.5),
                point=(0.5, 0.5),
                img=circleThis,
                keep_ratio=True
            )
            continue
        if arrival:
            # 后方站绘制
            baseCanvas.linePanel.recLine.__dict__["station_{}".format(sta.identifier)] = Img(
                uv_size=(1, 1),
                box_size=box_size,
                parent_point=(distance * i, 0.5),
                point=(0.5, 0.5),
                img=circleForward,
                keep_ratio=True
            )
        else:
            # 前方站绘制
            baseCanvas.linePanel.recLine.__dict__["station_{}".format(sta.identifier)] = Img(
                uv_size=(1, 1),
                box_size=box_size,
                parent_point=(distance * i, 0.5),
                point=(0.5, 0.5),
                img=circlePassed,
                keep_ratio=True
            )
    return baseCanvas


def generate_platform_sign(name: str, aliases: List[str], lineInfo: List[Line], entranceIdentifier: str, ratio: tuple[int | float, int | float],
                           reso: int = resolution
                           ):
    pass

# def main():
#     generate_entrance_sign(
#         "璧山",
#         aliases=["Bishan"],
#         lineInfo=[
#
#                 Line(identifier="2", chineseName="1号线", englishName="Line 1", color=Color.RED, stations=[]),
#                 Line(identifier="3", chineseName="27号线", englishName="Line 27", color="#685bc7", stations=[]),
#                 Line(identifier="1", chineseName="璧铜线", englishName="BT Line", color="#685BC7", stations=[]),
#         ],
#         entranceIdentifier="1",
#         ratio=(8, 1)
#     )
#
#
# main()
