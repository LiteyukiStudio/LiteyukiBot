import json
import locale
import os
import traceback
from typing import Dict, List, Any

from nonebot import logger

from src.api.data import Data

# global variable
language_data: Dict[str, Dict[str, str]] = dict()
resource_data: Dict[str, List[str]] = dict()

# 按照优先级排序
loaded_resource_packs: List['ResourcePack'] = list()

# system language
system_lang = locale.getdefaultlocale()[0]
if not isinstance(system_lang, str): system_lang = 'en_US'

"""
Language Data
{
    "zh_CN":{
        "example.text": "Hello World"
    }
}
"""


class Language:
    def __init__(self, lang: str = system_lang, quote: str = system_lang, fallback: str = 'en_US'):
        """语言类

        :param lang: 语言id，例如zh_CN，en_US
        :param quote: 语言引用，例如中文（新加坡）可引用于中文（简体），避免重复造轮子
        :param fallback: 语言回退，当目前语言和引用语言均没有时，回退到en_US（默认）
        """

        self.lang = lang

        if self.lang not in language_data: language_data[self.lang] = dict()
        self.language_data = language_data[self.lang]

        self.quote = self.language_data.get('quote', quote)
        self.fallback = fallback

    def get(self, key: str, **kwargs) -> str | Any:
        """获取本地化键名的值

        :param key:
        :return:
        """

        val = self.language_data.get(key, language_data.get(self.quote).get(key, language_data.get(self.fallback).get(key, key)))
        if isinstance(val, str):
            return val.format(**kwargs)
        else:
            return val

    def add(self, key: str, value: Any):
        """添加一个新词条

        :param key: 本地化键名
        :param value: 键值
        :return:
        """
        self.language_data[key] = value

    def add_data(self, data: dict):
        """添加一组键值对词条

        :param data:
        :return:
        """
        self.language_data.update(data)

    @staticmethod
    def load_file(fp: str):

        f = open(fp, 'r', encoding='utf-8')
        lang = os.path.basename(fp).split('.')[0]
        language = Language(lang)

        if fp.endswith('lang'):
            for line in f.read().splitlines():
                language.add(line.split('=')[0], line.split('=')[-1])
        elif fp.endswith('json'):
            language.add_data(json.load(f))

    @staticmethod
    def get_user_language(user_id: int) -> 'Language':
        db = Data('user', f'u{user_id}')
        return Language(db.get('language', system_lang))


class ResourcePack:

    def __init__(self, path: str):
        """

        :param path: resource pack dir path(include metadata.json)
        """
        self.path = path
        self.dir_name = os.path.basename(self.path)
        try:
            metadata = json.load(open(os.path.join(path, 'metadata.json'), 'r', encoding='utf-8'))
            self.name = metadata.get('name', self.dir_name)
            self.description = metadata.get('description', 'main.no_details')
        except BaseException as e:
            logger.error(Language().get('log.main.load_resource_error'))

    def __str__(self):
        return f'<ResourcePack {self.dir_name} {Language().get(self.name)}>'

    def load(self):
        self.load_language()
        self.load_file_path()
        loaded_resource_packs.insert(0, self)
        logger.success(Language().get('log.main.suc_to_load_resource', NAME=self.name))

    def load_language(self):
        texts_path = os.path.join(self.path, 'texts')
        if os.path.exists(texts_path):
            for lang_file in os.listdir(texts_path):
                Language.load_file(os.path.join(self.path, 'texts', lang_file))

    def load_file_path(self):
        for path, folders, files in os.walk(self.path):
            for f in files:
                file_index = os.path.join(path, f).replace(self.path + os.path.sep, '')
                file_path = os.path.join(path, f)
                file_index = file_index.replace('\\', '/')
                if file_index in resource_data:
                    resource_data[file_index].insert(0, file_path)
                else:
                    resource_data[file_index] = [file_path]


def load_resource_from_index():
    resource_index: list = Data('common', 'config').get('resource_index', [])
    resource_index.insert(0, 'vanilla_pack')
    for dir_name in resource_index:
        resource_pack = ResourcePack(os.path.join('resources', dir_name))
        try:
            resource_pack.load()
        except BaseException as e:
            traceback.print_exc()


def get_resource_path(resource_name: str) -> str:
    pass