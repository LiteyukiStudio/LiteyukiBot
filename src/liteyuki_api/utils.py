import os
import traceback
from typing import Tuple, Dict

import nonebot
import requests
from .canvas import Text


def clamp(x, _min, _max):
    if x < _min:
        return _min
    elif _min <= x <= _max:
        return x
    else:
        return _max


def download_file(url, file, chunk_size=1024):
    """
    url: file url
    file: 文件另存为路径
    chunk_size: chunk size
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.66 Safari/537.36'}
        if not os.path.exists(os.path.dirname(file)):
            os.makedirs(os.path.dirname(file))
        response_data_file = requests.get(url, stream=True, headers=headers)
        with open(file, 'wb') as f:
            for chunk in response_data_file.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
        nonebot.logger.info("下载成功： %s" % url)
    except BaseException as e:
        nonebot.logger.warning("下载失败: %s\n%s" % (url, traceback.format_exception(e)))


class Command:

    @staticmethod
    def get_keywords(old_dict: dict, keywords: dict) -> dict:
        """
        :param keywords:
        :param old_dict:
        :return:

        提取旧字典中设定键合成新字典
        """
        new = dict()
        for key in keywords:
            new[key] = old_dict.get(key, keywords[key])
        return new

    @staticmethod
    def formatToCommand(cmd: str, sep: str = " ", kw=True) -> Tuple[Tuple, Dict]:
        """
        :param kw: 将有等号的词语分出
        :param sep: 分隔符,默认空格
        :param cmd: "arg1 arg2 para1=value1 para2=value2"
        :return:

        命令参数处理
        自动cq去义
        "%20"表示空格
        """
        cmd = Command.escape(cmd, blank=False)
        cmd_list = cmd.strip().split(sep)
        args = []
        keywords = {}
        for arg in cmd_list:
            arg = arg.replace("%20", " ")
            if "=" in arg and kw:
                keywords[arg.split("=")[0]] = "=".join(arg.split("=")[1:])
            else:
                args.append(arg)
        return tuple(args), keywords

    @staticmethod
    def formatToString(*args, **keywords) -> str:

        """
        :param args:
        :param keywords:
        :return:
        escape会将空格转为%20，默认False不转，会将空格转为%20
        """

        string = ""
        for arg in args:
            string += Command.escape(arg) + " "
        kw_item = keywords.items()
        for item in kw_item:
            kw = ("%s=%s" % (item[0], item[1]))
            string += Command.escape(kw) + " "
        return string[:-1]

    @staticmethod
    def escape(text: str, blank=True) -> str:
        """
        CQ码去义

        :param text:
        :param blank: 转义%20为空格
        :return:
        """
        escape_data = {
            "&amp;": "&",
            "&#91;": "[",
            "&#93;": "]",
            "&#44;": ","
        }
        for esd in escape_data.items():
            text = text.replace(esd[0], esd[1])
        return text.replace("%20", " " if blank else "%20")
