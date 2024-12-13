from nonebot.adapters import satori


async def count_groups(bot: satori.Bot) -> int:
    cnt: int = 0

    group_response = await bot.guild_list()
    while group_response.next is not None:
        cnt += len(group_response.data)
        group_response = await bot.friend_list(next_token=group_response.next)

    cnt += len(group_response.data)
    return cnt - 1
