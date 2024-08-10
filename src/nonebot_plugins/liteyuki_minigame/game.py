import random
from pydantic import BaseModel
from src.utils.message.message import MarkdownMessage as md

class Dot(BaseModel):
    row: int
    col: int
    mask: bool = True
    value: int = 0
    flagged: bool = False


class Minesweeper:
    # 0-8: number of mines around, 9: mine, -1: undefined
    NUMS = "⓪①②③④⑤⑥⑦⑧🅑⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
    MASK = "🅜"
    FLAG = "🅕"
    MINE = "🅑"

    def __init__(self, rows, cols, num_mines, session_type, session_id):
        assert rows > 0 and cols > 0 and 0 < num_mines < rows * cols
        self.session_type = session_type
        self.session_id = session_id
        self.rows = rows
        self.cols = cols
        self.num_mines = num_mines
        self.board: list[list[Dot]] = [[Dot(row=i, col=j) for j in range(cols)] for i in range(rows)]
        self.is_first = True

    def reveal(self, row, col) -> bool:
        """
        展开
        Args:
            row:
            col:

        Returns:
            游戏是否继续

        """

        if self.is_first:
            # 第一次展开，生成地雷
            self.generate_board(self.board[row][col])
            self.is_first = False

        if self.board[row][col].value == 9:
            self.board[row][col].mask = False
            return False

        if not self.board[row][col].mask:
            return True

        self.board[row][col].mask = False

        if self.board[row][col].value == 0:
            self.reveal_neighbors(row, col)
        return True

    def is_win(self) -> bool:
        """
        是否胜利
        Returns:
        """
        for row in range(self.rows):
            for col in range(self.cols):
                if self.board[row][col].mask and self.board[row][col].value != 9:
                    return False
        return True

    def generate_board(self, first_dot: Dot):
        """
        避开第一个点，生成地雷
        Args:
            first_dot: 第一个点

        Returns:

        """
        generate_count = 0
        while generate_count < self.num_mines:
            row = random.randint(0, self.rows - 1)
            col = random.randint(0, self.cols - 1)
            if self.board[row][col].value == 9 or (row, col) == (first_dot.row, first_dot.col):
                continue
            self.board[row][col] = Dot(row=row, col=col, mask=True, value=9)
            generate_count += 1

        for row in range(self.rows):
            for col in range(self.cols):
                if self.board[row][col].value != 9:
                    self.board[row][col].value = self.count_adjacent_mines(row, col)

    def count_adjacent_mines(self, row, col):
        """
        计算周围地雷数量
        Args:
            row:
            col:

        Returns:

        """
        count = 0
        for r in range(max(0, row - 1), min(self.rows, row + 2)):
            for c in range(max(0, col - 1), min(self.cols, col + 2)):
                if self.board[r][c].value == 9:
                    count += 1
        return count

    def reveal_neighbors(self, row, col):
        """
        递归展开，使用深度优先搜索
        Args:
            row:
            col:

        Returns:

        """
        for r in range(max(0, row - 1), min(self.rows, row + 2)):
            for c in range(max(0, col - 1), min(self.cols, col + 2)):
                if self.board[r][c].mask:
                    self.board[r][c].mask = False
                    if self.board[r][c].value == 0:
                        self.reveal_neighbors(r, c)

    def mark(self, row, col) -> bool:
        """
        标记
        Args:
            row:
            col:
        Returns:
            是否标记成功，如果已经展开则无法标记
        """
        if self.board[row][col].mask:
            self.board[row][col].flagged = not self.board[row][col].flagged
        return self.board[row][col].flagged

    def board_markdown(self) -> str:
        """
        打印地雷板
        Returns:
        """
        dis = " "
        start = "> " if self.cols >= 10 else ""
        text = start + self.NUMS[0] + dis*2
        # 横向两个雷之间的间隔字符
        # 生成横向索引
        for i in range(self.cols):
            text += f"{self.NUMS[i]}" + dis
        text += "\n\n"
        for i, row in enumerate(self.board):
            text += start + f"{self.NUMS[i]}" + dis*2
            for dot in row:
                if dot.mask and not dot.flagged:
                    text += md.btn_cmd(self.MASK, f"minesweeper reveal {dot.row} {dot.col}")
                elif dot.flagged:
                    text += md.btn_cmd(self.FLAG, f"minesweeper mark {dot.row} {dot.col}")
                else:
                    text += self.NUMS[dot.value]
                text += dis
            text += "\n"
        btn_mark = md.btn_cmd("标记", f"minesweeper mark ", enter=False)
        btn_end = md.btn_cmd("结束", "minesweeper end", enter=True)
        text += f"    {btn_mark}   {btn_end}"
        return text
