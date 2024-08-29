# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 下午10:52
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : on.py
@Software: PyCharm
"""

from queue import Queue

from liteyuki.comm.storage import shared_memory
from liteyuki.log import logger
from liteyuki.message.event import MessageEvent
from liteyuki.message.matcher import Matcher
from liteyuki.message.rule import Rule, empty_rule

_matcher_list: list[Matcher] = []
_queue: Queue = Queue()


@shared_memory.on_subscriber_receive("event_to_liteyuki")
async def _(event: MessageEvent):
    print("AA")
    current_priority = -1
    for i, matcher in enumerate(_matcher_list):
        logger.info(f"Running matcher {matcher} for event: {event}")
        await matcher.run(event)
        # 同优先级不阻断，不同优先级阻断
        if current_priority != matcher.priority:
            current_priority = matcher.priority
            if matcher.block:
                break
    else:
        logger.info(f"No matcher matched for event: {event}")
    print("BB")


def add_matcher(matcher: Matcher):
    for i, m in enumerate(_matcher_list):
        if m.priority < matcher.priority:
            _matcher_list.insert(i, matcher)
            break
    else:
        _matcher_list.append(matcher)


def on_message(rule: Rule = empty_rule, priority: int = 0, block: bool = False) -> Matcher:
    matcher = Matcher(rule, priority, block)
    # 按照优先级插入
    add_matcher(matcher)
    return matcher


def on_keywords(keywords: list[str], rule=empty_rule, priority: int = 0, block: bool = False) -> Matcher:
    @Rule
    async def on_keywords_rule(event: MessageEvent):
        return any(keyword in event.raw_message for keyword in keywords)

    return on_message(on_keywords_rule & rule, priority, block)
