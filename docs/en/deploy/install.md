---
title: Install
order: 1
---
# Install

## **Normal Installation**

1. Install [`Git`](https://git-scm.com/download/) and [`Python3.10+`](https://www.python.org/downloads/release/python-31010/) Environment.

```bash
# Clone the project
git clone https://github.com/LiteyukiStudio/LiteyukiBot --depth=1
# change directory
cd LiteyukiBot
# install dependencies
pip install -r requirements.txt
# start the bot!
python main.py
```

> [!tip]
> It is recommended to use a virtual environment to run Liteyuki to avoid dependency conflicts. 
> You can use `python -m venv .venv` to create a virtual environment, and then use `.venv\Scripts\activate` to activate the virtual environment 
> (use `source .venv/bin/activate` to activate on Linux).


## **Run with Docker**

1. Install [`Docker`](https://docs.docker.com/get-docker/)
2. Clone Repo `git clone https://github.com/LiteyukiStudio/LiteyukiBot --depth=1` 
3. Change directory `cd LiteyukiBot`
4. Build docker image `docker build -t liteyukibot .`
5. Run container `docker run -p 20216:20216 -v $(pwd):/liteyukibot -v $(pwd)/.cache:/root/.cache liteyukibot`

> [!tip]
> If you are using Windows, please use the absolute project directory `/path/to/LiteyukiBot` instead of `$&#40;pwd&#41;` <br>
> If you have modified the port number, please replace `20216:20216` with your port number

## **Use TRSS Script**
 [TRSS_Liteyuki Management Script](https://timerainstarsky.github.io/TRSS_Liteyuki/), which provides a more convenient way to manage LiteyukiBot, recommended to use `Arch Linux`


## **Device Requirements**
- Windows system version minimum `Windows10+`/`Windows Server 2019+`
- Linux system requires Python3.10+, recommended `Ubuntu 20.04+`
- CPU: at least `1vCPU`
- Memory: Bot without other plugins will occupy `300~500MB`, including `chromium` and `node` processes, other plugins depend on specific plugins, recommended `1GB` or more
- Disk: at least `1GB` of space

> [!warning]
> If there are multiple environments on the device, please use `path/to/python -m pip install -r requirements.txt` to install dependencies, `path/to/python` is the path to your Python executable

> [!warning]
> Liteyuki's update function depends on Git. If you do not have Git installed and run the source code directly, you will not be able to use the update function

#### For other questions, please refer to [FAQ](./fandq)