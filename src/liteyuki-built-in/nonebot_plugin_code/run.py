# python3
# -*- coding: utf-8 -*-
# @Time    : 2021/11/22 14:17
# @Author  : yzyyz
# @Email   :  youzyyz1384@qq.com
# @File    : run.py
# @Software: PyCharm
import aiohttp
import re

codeType = {
    'py': ['python', 'py'],
    'cpp': ['cpp', 'cpp'],
    'java': ['java', 'java'],
    'php': ['php', 'php'],
    'js': ['javascript', 'js'],
    'c': ['c', 'c'],
    'c#': ['csharp', 'cs'],
    'go': ['go', 'go'],
    'asm': ['assembly', 'asm']
}


async def run(strcode):
    strcode = strcode.replace('&amp;', '&').replace('&#91;', '[').replace('&#93;', ']')
    try:
        a = re.findall(r'(py|php|java|cpp|js|c#|c|go|asm)\s?(-i)?\s?(\w*)?([\r\n])((?:.|\n)+)', strcode)[0]
    except BaseException:
        return "输入有误汪\n目前仅支持c/cpp/c#/py/php/go/java/js"
    if "-i" in strcode:
        lang, code = a[0], a[4]
        dataJson = {
            "files": [
                {
                    "name": f"main.{codeType[lang][1]}",
                    "content": code
                }
            ],
            "stdin": a[2],
            "command": ""
        }
    else:
        lang, code = a[0], a[4]
        dataJson = {
            "files": [
                {
                    "name": f"main.{codeType[lang][1]}",
                    "content": code
                }
            ],
            "stdin": "",
            "command": ""
        }
    headers = {
        "Authorization": "Token 0123456-789a-bcde-f012-3456789abcde",
        "content-type": "application/"
    }
    async with aiohttp.request("POST", url=f'https://glot.io/run/{codeType[lang][0]}?version=latest', headers=headers, json=dataJson) as res:
        if res.status == 200:
            res = await res.json()
            if res['stdout'] != "":
                return res['stdout']
            else:
                return res['stderr'].strip()
