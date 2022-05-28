import shutil

from nonebot import require

from extraApi.base import *

scheduler = require("nonebot_plugin_apscheduler").scheduler


@scheduler.scheduled_job("cron", hour="0", minute="30", second="0")
@run_sync
def backup():
    f = "backup_%s-%s-%s-%s-%s-%s" % tuple(list(time.localtime())[0:6])
    folder = os.path.join(ExConfig.data_backup_path, f)
    os.makedirs(folder)
    n = 0
    for data_json in os.listdir(ExConfig.data_path):
        whole_path = os.path.join(ExConfig.data_path, data_json)
        shutil.copy(whole_path, os.path.join(folder, data_json))
        n += 1
    return f, n

@run_sync
def update_move():
    for f in os.listdir(os.path.join(ExConfig.cache_path, "new_code/Liteyuki-master")):
        try:
            shutil.move(os.path.join(ExConfig.cache_path, "new_code/Liteyuki-master", f), ExConfig.root_path)
        except BaseException:
            pass
