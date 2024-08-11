FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/python:3.10-slim-bullseye

ENV TZ Asia/Shanghai

COPY docker/sources.list /etc/apt/sources.list

RUN apt-get update && apt-get install -y git

WORKDIR /liteyukibot

COPY . /liteyukibot

RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

RUN apt-get install -y libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libxkbcommon0 libasound2

EXPOSE 20216

CMD ["python", "main.py"]