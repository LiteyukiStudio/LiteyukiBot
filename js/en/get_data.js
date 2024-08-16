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

            Instances:<span id="total">${globalTotal}</span>&nbsp;&nbsp;&nbsp;&nbsp;Online:<span id="online">${globalOnline}</span></div>`;

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