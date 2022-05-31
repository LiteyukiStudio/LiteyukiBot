import os
import shutil

from nonebot import require

from ..extraApi.base import *
import zipfile

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
    zf = zipfile.ZipFile(os.path.join(ExConfig.res_path, "version/new_code.zip"))
    zf.extractall(os.path.join(ExConfig.cache_path))

    def bianli(path, short):
        for f in os.listdir(path):
            short2 = os.path.join(short, f)
            whole = os.path.join(path, f)
            if os.path.isdir(whole):
                bianli(whole, short2)
            else:
                print(whole, os.path.join(ExConfig.root_path, short2))
                shutil.copyfile(whole, os.path.join(ExConfig.root_path, short2))

    bianli(os.path.join(ExConfig.cache_path, "Liteyuki-master"), "")
