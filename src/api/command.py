from typing import List, Any, Tuple, Dict

from src.api.adapter import Bot


async def run_function(bot: Bot, function_name: str) -> List[Any]:
    await bot.call_api()


async def run_command(bot: Bot, cmd: str) -> Any:
    await bot.call_api()


def message_unescape(message: str):
    """把那堆乱七八糟的文本转回原始文本

    :param message:
    :return:
    """
    data = {
        '&amp;': '&',
        '&#91;': '[',
        '&#93;': ']',
        '&#44;': ',',
        '%20': ' '
    }
    for old, new in data.items():
        message = message.replace(old, new)
    return message


def format_command(command_str: str) -> Tuple[str, Tuple[str], Dict[str, str]]:
    args, kwargs = [], {}
    for element in command_str.split(' '):
        if '=' in element:
            kwargs[element.split('=')[0]] = kwargs[element.split('=')[1]]
        else:
            args.append(element)