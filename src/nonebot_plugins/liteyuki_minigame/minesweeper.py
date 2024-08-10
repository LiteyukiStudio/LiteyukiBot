from nonebot import require

from src.utils.base.ly_typing import T_Bot, T_MessageEvent
from src.utils.message.message import MarkdownMessage as md

require("nonebot_plugin_alconna")
from .game import Minesweeper

from nonebot_plugin_alconna import Alconna, on_alconna, Subcommand, Args, Arparma

minesweeper = on_alconna(
    aliases={"扫雷"},
    command=Alconna(
        "minesweeper",
        Subcommand(
            "start",
            Args["row", int, 8]["col", int, 8]["mines", int, 10],
            alias=["开始"],

        ),
        Subcommand(
            "end",
            alias=["结束"]
        ),
        Subcommand(
            "reveal",
            Args["row", int]["col", int],
            alias=["展开"]

        ),
        Subcommand(
            "mark",
            Args["row", int]["col", int],
            alias=["标记"]
        ),
    ),
)

minesweeper_cache: list[Minesweeper] = []


def get_minesweeper_cache(event: T_MessageEvent) -> Minesweeper | None:
    for i in minesweeper_cache:
        if i.session_type == event.message_type:
            if i.session_id == event.user_id or i.session_id == event.group_id:
                return i
    return None


@minesweeper.handle()
async def _(event: T_MessageEvent, result: Arparma, bot: T_Bot):
    game = get_minesweeper_cache(event)
    if result.subcommands.get("start"):
        if game:
            await minesweeper.finish("当前会话不能同时进行多个扫雷游戏")
        else:
            try:
                new_game = Minesweeper(
                    rows=result.subcommands["start"].args["row"],
                    cols=result.subcommands["start"].args["col"],
                    num_mines=result.subcommands["start"].args["mines"],
                    session_type=event.message_type,
                    session_id=event.user_id if event.message_type == "private" else event.group_id,
                )
                minesweeper_cache.append(new_game)
                await minesweeper.send("游戏开始")
                await md.send_md(new_game.board_markdown(), bot, event=event)
            except AssertionError:
                await minesweeper.finish("参数错误")
    elif result.subcommands.get("end"):
        if game:
            minesweeper_cache.remove(game)
            await minesweeper.finish("游戏结束")
        else:
            await minesweeper.finish("当前没有扫雷游戏")
    elif result.subcommands.get("reveal"):
        if not game:
            await minesweeper.finish("当前没有扫雷游戏")
        else:
            row = result.subcommands["reveal"].args["row"]
            col = result.subcommands["reveal"].args["col"]
            if not (0 <= row < game.rows and 0 <= col < game.cols):
                await minesweeper.finish("参数错误")
            if not game.reveal(row, col):
                minesweeper_cache.remove(game)
                await md.send_md(game.board_markdown(), bot, event=event)
                await minesweeper.finish("游戏结束")
            await md.send_md(game.board_markdown(), bot, event=event)
            if game.is_win():
                minesweeper_cache.remove(game)
                await minesweeper.finish("游戏胜利")
    elif result.subcommands.get("mark"):
        if not game:
            await minesweeper.finish("当前没有扫雷游戏")
        else:
            row = result.subcommands["mark"].args["row"]
            col = result.subcommands["mark"].args["col"]
            if not (0 <= row < game.rows and 0 <= col < game.cols):
                await minesweeper.finish("参数错误")
            game.board[row][col].flagged = not game.board[row][col].flagged
            await md.send_md(game.board_markdown(), bot, event=event)
    else:
        await minesweeper.finish("参数错误")
