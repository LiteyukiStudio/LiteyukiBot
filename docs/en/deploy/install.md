---
title: Installation
icon: download
order: 1
category: deployment
tag:
  - 安装
---

## **Installation**

### **Conventional deployment**

1. Install [`Git`](https://git-scm.com/download/) and [`Python3.10+`](https://www.python.org/downloads/release/python-31010/) environment

```bash
# Clone the project locally, --depth=1 to reduce the size of the cloned repository, this project updates depend on Git
git clone https://github.com/LiteyukiStudio/LiteyukiBot --depth=1
# change the directory to the project root
cd LiteyukiBot
# install the project dependencies
pip install -r requirements.txt
# start bot
python main.py
```

> [!tip]
> Recommended to use `venv` to run Liteyuki to avoid dependency conflicts, you can use `python -m venv .venv` to create a virtual environment, and then use `.venv\Scripts\activate` to activate the virtual environment (use `source .venv/bin/activate` to activate on Linux)

### **Use docker**

1. Install [`Docker`](https://docs.docker.com/get-docker/)
2. Clone project repo `git clone https://github.com/LiteyukiStudio/LiteyukiBot --depth=1` 
3. change directory `cd LiteyukiBot`
4. build image with `docker build -t liteyukibot .`
5. start container `docker run -p 20216:20216 -v $(pwd):/liteyukibot -v $(pwd)/.cache:/root/.cache liteyukibot`

> [!tip]
> For Windows, please use the absolute project directory `/path/to/LiteyukiBot` instead of $(pwd) 
>
> If you have changed the port number, replace `20216` in `20216:20216` with your port number

### **Use TRSS Scripts**
 [TRSS_Liteyuki LiteyukiBot manage script](https://timerainstarsky.github.io/TRSS_Liteyuki/), This feature is supported by TRSS and is not an official feature of LiteyukiBot. It is recommended to use Arch Linux.


## **Device requirements**

- Minimum Windows system version: `Windows 10+` / `Windows Server 2019+`
- Linux systems need to support Python 3.10+, with `Ubuntu 20.04+` recommended
- CPU: `1 vCPU` and more(Bot is multi processes, the more cores, the better the performance)
- Memory: Without other plugins, the Bot will occupy `300~500MB`, including processes like `chromium` and `node`. The memory occupied by other plugins depends on the specific plugins, and it is recommended to have more than `1GB`.
- Storage: At least `1GB` of space is required.

> [!warning]
> If there are multiple environments on the device, please use `path/to/python -m pip install -r requirements.txt` to install dependencies, where `path/to/python` is the path to your Python executable.

> [!warning]
> The update feature of Liteyuki depends on Git. If you have not installed Git and directly download the source code to run, you will not be able to use the update feature.

#### For other issues, please go to [Q&A](/deployment/fandq)