import nonebot

from nonebot.adapters import satori
from nonebot.adapters.satori.models import User


class UserInfo:
    user_infos: dict = {}

    async def load_friends(self, bot: satori.Bot):
        nonebot.logger.info("Update user info from friends")
        friend_response = await bot.friend_list()
        while friend_response.next is not None:
            for i in friend_response.data:
                i: User = i
                self.user_infos[str(i.id)] = i
            friend_response = await bot.friend_list(next_token=friend_response.next)

        for i in friend_response.data:
            i: User = i
            self.user_infos[str(i.id)] = i

        nonebot.logger.info("Finish update user info")

    async def get(self, uid: int | str) -> User | None:
        try:
            return self.user_infos[str(uid)]
        except KeyError:
            return None

    async def put(self, user: User):
        self.user_infos[str(user.id)] = user

    def __init__(self):
        pass


user_infos = UserInfo()
