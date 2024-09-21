"""
从markdown提取插件/资源信息
"""
from typing import Any

from github.Issue import Issue

from liteyuki_flow.typ import Nil, err, nil  # type: ignore


# # xxx
class Header:
    def __init__(self, level: int, content: str):
        self.level = level
        self.content = content

    def __str__(self):
        return f'Header({self.level}, {self.content})'

    def __repr__(self):
        return self.__str__()


# - xxx
class List:
    def __init__(self, level: int, content: str):
        self.level = level
        self.content = content

    def __str__(self):
        return f'List({self.level}, {self.content})'

    def __repr__(self):
        return self.__str__()


class FrontMatter:
    def __init__(self, content: dict[str, str]):
        self.content = content

    def __setitem__(self, key: str, value: str):
        self.content[key] = value

    def get(self, key, default=None) -> Any:
        return self.content.get(key, default)

    def __str__(self):
        return "\n".join([f'{k}: {v}' for k, v in self.content.items()])


class MarkdownParser:
    def __init__(self, content: str):
        self.content = content
        self.content_lines = content.split('\n')
        self.front_matters: FrontMatter = FrontMatter({})

        self._content_list: list[Any] = [self.front_matters]

        self.lineno = 0

        self._parsed = False

    def parse_front_matters(self) -> err:
        if self.content_lines[self.lineno].strip() != '---':
            return ValueError('Invalid front matter')
        while self.lineno < len(self.content_lines):
            self._next_line()
            line = self.content_lines[self.lineno]
            if line.strip() == '---':
                break
            if line.strip().startswith('#'):
                # fm注释
                continue
            try:
                key, value = line.split(':', 1)
            except ValueError:
                return Exception(f'Invalid front matter: {line}')
            self.front_matters[key.strip()] = value.strip()
        return nil

    def build_front_matters(self) -> str:
        return "---\n" + str(self.front_matters) + "\n---"

    def _parse_content(self) -> tuple[list[Any], err]:
        content: list[Any] = []
        while self.lineno < len(self.content_lines):
            item, e = self._parse_line()
            if e != nil:
                return nil, e
            content.append(item)
        return content, nil

    def _parse_line(self) -> tuple[Any, err]:
        line = self.content_lines[self.lineno]
        if line.startswith('#'):
            # 计算start有几个#
            start = 0
            while line[start] == '#':
                start += 1
            return Header(start, line[start:].strip()), nil
        elif line.startswith('-'):
            start = 0
            while line[start] == '-':
                start += 1
            return List(start, line[start:].strip()), nil

        # 处理<!--注释 continue
        elif line.strip().startswith('<!--'):
            while not line.strip().endswith('-->'):
                self._next_line()
                line = self.content_lines[self.lineno]
            return None, nil
        # 处理[//]: # (注释) continue
        elif line.strip().startswith('[//]: #'):
            self._next_line()
            return None, nil

        self._next_line()
        return nil, ValueError(f'Invalid line: {line}')

    def _next_line(self):
        self.lineno += 1

    def parse(self) -> tuple[list[Any] | Nil, err]:
        if self._parsed:
            return self._content_list, nil

        e = self.parse_front_matters()
        if e != nil:
            return nil, e

        ls, e = self._parse_content()
        if e != nil:
            return nil, e

        self._content_list.extend(ls)
        self._parsed = True

        return self._content_list, nil


# 解析资源发布issue体
def parse_resource_publish_info(issue: Issue) -> dict[str, str]:
    parser = MarkdownParser(issue.body)
    parser.parse_front_matters()
    return parser.front_matters