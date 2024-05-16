from nonebot.adapters import satori


async def count_friends(bot: satori.Bot) -> int:
    cnt: int = 0

    friend_response = await bot.friend_list()
    while friend_response.next is not None:
        cnt += len(friend_response.data)
        friend_response = await bot.friend_list(next_token=friend_response.next)

    cnt += len(friend_response.data)
    return cnt - 1
