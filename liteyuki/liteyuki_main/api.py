import nonebot
from git import Repo

remote_urls = [
        "https://github.com/snowykami/LiteyukiBot.git",
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
    # origins = ["origin", "origin2"]
    # repo = Repo(".")
    #
    # # Get the current HEAD commit
    # current_head_commit = repo.head.commit
    #
    # # Fetch the latest information from the cloud
    # repo.remotes.origin.fetch()
    #
    # # Get the latest HEAD commit
    # new_head_commit = repo.commit('origin/main')
    #
    # # If the new HEAD commit is different from the current HEAD commit, there is a new commit
    # diffs = current_head_commit.diff(new_head_commit)
    # logs = ""
    # for diff in diffs.iter_change_type('M'):
    #     logs += f"\n{diff.a_path}"
    #
    # for origin in origins:
    #     try:
    #         repo.remotes[origin].pull()
    #         break
    #     except Exception as e:
    #         nonebot.logger.error(f"Pull from {origin} failed: {e}")
    #         continue
    # else:
    #     return False, 0
    #
    # return True, len(logs)
    new_commit_detected = detect_update()
    if new_commit_detected:
        repo = Repo(".")
        logs = ""
        # 对每个远程仓库进行更新
        for remote_url in remote_urls:
            repo.remotes.origin.set_url(remote_url)
            repo.remotes.origin.pull()
            diffs = repo.head.commit.diff("origin/main")

            for diff in diffs.iter_change_type('M'):
                logs += f"\n{diff.a_path}"
        return True, logs
    else:
        return False, "Nothing Changed"

