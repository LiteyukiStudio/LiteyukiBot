api send_private_msg user_id=qq message=msg
sleep 3

# 使用asyncio.create_task()创建一个新的任务，不等待任务完成直接执行下一条命令
nohup function hello

sleep 10

# cancel所有的tasks
end