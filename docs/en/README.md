---
home: true
icon: home
title: Home
heroImage: https://cdn.liteyuki.icu/static/svg/lylogo-full.svg
heroImageDark: https://cdn.liteyuki.icu/static/svg/lylogo-full-dark.svg
bgImage:
bgImageDark:
bgImageStyle:
  background-attachment: fixed
heroText: LiteyukiBot
tagline: LiteyukiBot A high-performance, easy-to-use chatbot framework and application
 
actions:
  - text: Get Started
    icon: rocket
    link: ./deployment/install.html
    type: primary

  - text: Usage
    icon: book
    link: ./usage/basic_command.html

highlights:
  - header: Simple and Efficient
    image: /assets/image/layout.svg
    bgImage: https://theme-hope-assets.vuejs.press/bg/2-light.svg
    bgImageDark: https://theme-hope-assets.vuejs.press/bg/2-dark.svg
    bgImageStyle:
      background-repeat: repeat
      background-size: initial
    features:
      - title: Multi-Framework Support
        icon: robot
        details: Compatible with nonebot, melobot, etc., with good ecological support
        link: https://nonebot.dev/

      - title: Convenient Management
        icon: plug
        details: Use package manager to manage plugins and resource packs

      - title: Custom Themes Support
        icon: paint-brush
        details: Fully customize the appearance with resource packs
        link: https://bot.liteyuki.icu/usage/resource_pack.html

      - title: i18n
        icon: globe
        details: Support multiple languages through resource packs
        link: https://baike.baidu.com/item/i18n/6771940

      - title: Easy to Use
        icon: cog
        details: No need for cumbersome pre-processes, ready to use
        link: https://bot.liteyuki.icu/deployment/config.html

      - title: High Performance
        icon: tachometer-alt
        details: 500 plugins, start within 2s

      - title: Rolling Update
        icon: cloud-download
        details: Keep your bot up to date

      - title: OpenSource
        icon: code
        details: MIT LICENCE open source project, welcome your contribution

  - header: Quick Start
    image: /assets/image/box.svg
    bgImage: https://theme-hope-assets.vuejs.press/bg/3-light.svg
    bgImageDark: https://theme-hope-assets.vuejs.press/bg/3-dark.svg
    highlights:
      - title: Install Git and Python3.10+ environment
      - title: Use <code>git clone https://github.com/LiteyukiStudio/LiteyukiBot --depth=1</code> to clone the project locally
      - title: Use <code>cd LiteyukiBot</code> to change the directory to the project root
      - title: Use <code>pip install -r requirements.txt</code> install the project dependencies
        details: If you have multiple Python environments, please use <code>pythonx -m pip install -r requirements.txt</code>.
      - title: Start bot with <code>python main.py</code>.
copyright: © 2021-2024 SnowyKami All Rights Reserved

---
<script>
// 定义全局变量来存储数据
let globalTotal = 0;
let globalOnline = 0;

// 从API获取数据并更新全局变量
function fetchAndUpdateData() {
    Promise.all([
        fetch("https://api.liteyuki.icu/count").then(res => res.json()),
        fetch("https://api.liteyuki.icu/online").then(res => res.json())
    ])
        .then(([countRes, onlineRes]) => {
            globalTotal = countRes.register;
            globalOnline = onlineRes.online;
        })
        .catch(err => {
            console.error("Error fetching data:", err);
        });
}

// 更新页面显示，使用全局变量中的数据
function updatePageDisplay() {
    let countInfo = document.getElementById("count-info");
    if (!countInfo) {
        let info = `<div id="count-info" style="text-align: center; font-size: 20px; font-weight: 500">
            Instances: <span id="total">${globalTotal}</span>&nbsp;&nbsp;&nbsp;&nbsp;Online: <span id="online">${globalOnline}</span></div>`;
        let mainDescription = document.querySelector("#main-description");
        if (mainDescription) {
            mainDescription.insertAdjacentHTML('afterend', info);
        }
    }
}

// 初始调用更新数据
fetchAndUpdateData();
updatePageDisplay();

// 设置定时器，分别以不同频率调用更新数据和更新页面的函数
setInterval(fetchAndUpdateData, 10000); // 每10秒更新一次数据
setInterval(updatePageDisplay, 1000); // 每1秒更新一次页面显示
</script> 