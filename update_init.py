import os

print("更新成功")
print("正在重启")
delete_list = [
    "src/liteyuki-built-in/kami_super_tool/restart.py"
]
for d_f in delete_list:
    try:
        os.remove(d_f)
    except:
        pass
