import nonebot
from git import Repo

from src.utils.base.config import get_config

remote_urls = [
        "https://github.com/LiteyukiStudio/LiteyukiBot.git",
        "https://gitee.com/snowykami/LiteyukiBot.git"
]


def detect_update() -> bool:
    # 对每个远程仓库进行检查，只要有一个仓库有更新，就返回True
    for remote_url in remote_urls:
        repo = Repo(".")
        repo.remotes.origin.set_url(remote_url)
        repo.remotes.origin.fetch()
        if repo.head.commit != repo.commit('origin/main'):
            return True


def update_liteyuki() -> tuple[bool, str]:
    """更新轻雪
    :return: 是否更新成功，更新变动"""

    if get_config("allow_update", True):
        new_commit_detected = detect_update()
        if new_commit_detected:
            repo = Repo(".")
            logs = ""
            # 对每个远程仓库进行更新
            for remote_url in remote_urls:
                try:
                    logs += f"\nremote: {remote_url}"
                    repo.remotes.origin.set_url(remote_url)
                    repo.remotes.origin.pull()
                    diffs = repo.head.commit.diff("origin/main")
                    for diff in diffs.iter_change_type('M'):
                        logs += f"\n{diff.a_path}"
                    return True, logs
                except:
                    continue
        else:
            return False, "Nothing Changed"

    else:
        raise PermissionError("Update is not allowed.")
