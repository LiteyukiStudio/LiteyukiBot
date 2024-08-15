const data = JSON.parse(document.getElementById('data').innerText);
const bot_data = data['bot'];  // 机器人数据
const hardwareData = data['hardware'];    // 硬件数据
const liteyukiData = data['liteyuki'];   // LiteYuki数据
const localData = data['localization'];    // 本地化语言数据

/**
 * 创建CPU/内存/交换饼图
 * @param title
 * @param {Array<{name: string, value: number}>} data 数据
 */
function createPieChartOption(title, data) {
    // data为各项占比列表
    return {
        animation: false,
        title: {
            text: title,
            left: 'center',
            top: 'center',
            textStyle: {
                color: '#fff',
                fontSize: 30,
                lineHeight: 36
            }
        },
        tooltip: {
            show: true,
            trigger: 'item',
            backgroundColor: '#fff',
        },
        color: data.length === 3 ? ['#00a6ff', '#a2d8f4', "#ffffff44"] : ['#a2d8f4', '#ffffff44'],
        series: [
            {
                name: 'info',
                type: 'pie',
                radius: ['80%', '100%'],
                center: ['50%', '50%'],
                itemStyle: {
                    normal: {
                        label: {
                            show: false
                        },
                        labelLine: {
                            show: false
                        }
                    },
                    emphasis: {
                        label: {
                            show: true,
                            textStyle: {
                                fontSize: '50',
                                fontWeight: 'bold'
                            }
                        }
                    }
                },
                data: data
            }
        ]
    }
}


function convertSize(size, precision = 2, addUnit = true, suffix = " XiB") {
    let isNegative = size < 0;
    size = Math.abs(size);
    let units = ["", "K", "M", "G", "T", "P", "E", "Z"];
    let unit = "";

    for (let i = 0; i < units.length; i++) {
        if (size < 1024) {
            unit = units[i];
            break;
        }
        size /= 1024;
    }

    if (isNegative) {
        size = -size;
    }

    if (addUnit) {
        return size.toFixed(precision) + suffix.replace('X', unit);
    } else {
        return size;
    }
}

/**
 * 创建磁盘用量柱状图
 * @param title
 * @param percent 数据
 */
function createBarChart(title, percent, name) {
    // percent为百分比，最大值为100
    let diskDiv = document.createElement('div');
    diskDiv.setAttribute('class', 'disk-info');
    diskDiv.style.marginBottom = '20px';
    diskDiv.innerHTML = `
        <div class="disk-name">${name}</div>
        <div class="disk-details">${title}</div>
        <div class="disk-usage" style="width: ${percent}%"></div>
    `;

    updateDiskNameWidth(diskDiv);

    return diskDiv;
}

// 更新 .disk-name 宽度
function updateDiskNameWidth(diskInfoElement) {
    let diskDetails = diskInfoElement.querySelector('.disk-details');
    let diskName = diskInfoElement.querySelector('.disk-name');
    let detailsWidth = diskDetails.offsetWidth;
    let parentWidth = diskInfoElement.offsetWidth;

    let nameMaxWidth = parentWidth - detailsWidth - 20 - 40;
    diskName.style.maxWidth = `${nameMaxWidth}px`;
}

function secondsToTextTime(seconds) {
    let days = Math.floor(seconds / 86400)
    let hours = Math.floor((seconds % 86400) / 3600)
    let minutes = Math.floor((seconds % 3600) / 60)
    let seconds_ = Math.floor(seconds % 60)
    return `${days}${localData['days']} ${hours}${localData['hours']} ${minutes}${localData['minutes']} ${seconds_}${localData['seconds']}`
}

// 主函数
function main() {
    // 添加机器人信息
    bot_data['bots'].forEach(
        (bot) => {
            let botInfoDiv = document.importNode(document.getElementById('bot-template').content, true)   // 复制模板


            // 设置机器人信息
            botInfoDiv.className = 'info-box bot-info'

            botInfoDiv.querySelector('.bot-icon-img').setAttribute('src', bot['icon'])
            botInfoDiv.querySelector('.bot-name').innerText = bot['name']
            let tagArray = [
                bot['protocol_name'],
                bot['app_name'],
                `${localData['groups']} ${bot['groups']}`,
                `${localData['friends']} ${bot['friends']}`,
                `${localData['message_sent']} ${bot['message_sent']}`,
                `${localData['message_received']} ${bot['message_received']}`,
            ]
            // 添加一些标签
            tagArray.forEach(
                (tag, index) => {
                    let tagSpan = document.createElement('span')
                    tagSpan.className = 'bot-tag'
                    tagSpan.innerText = tag
                    // 给最后一个标签不添加后缀
                    tagSpan.setAttribute('suffix', index === tagArray.length - 1 ? '0' : '1')
                    botInfoDiv.querySelector('.bot-tags').appendChild(tagSpan)
                }
            )
            document.body.insertBefore(botInfoDiv, document.getElementById('hardware-info'))    // 插入对象

        }
    )

    // 添加轻雪信息
    let liteyukiInfoDiv = document.importNode(document.getElementById('bot-template').content, true)   // 复制模板
    liteyukiInfoDiv.className = 'info-box bot-info'
    liteyukiInfoDiv.querySelector('.bot-icon-img').setAttribute('src', './img/liteyuki.png')
    liteyukiInfoDiv.querySelector('.bot-name').innerText = liteyukiData['name']

    let tagArray = [
        `Liteyuki ${liteyukiData['version']}`,
        `Nonebot ${liteyukiData['nonebot']}`,
        liteyukiData['python'],
        liteyukiData['system'],
        `${localData['plugins']} ${liteyukiData['plugins']}`,
        `${localData['resources']} ${liteyukiData['resources']}`,
        `${localData['bots']} ${liteyukiData['bots']}`,
        `${localData['runtime']} ${secondsToTextTime(liteyukiData['runtime'])}`,
    ]
    tagArray.forEach(
        (tag, index) => {
            let tagSpan = document.createElement('span')
            tagSpan.className = 'bot-tag'
            tagSpan.innerText = tag
            // 给最后一个标签不添加后缀
            tagSpan.setAttribute('suffix', index === tagArray.length - 1 ? '0' : '1')
            liteyukiInfoDiv.querySelector('.bot-tags').appendChild(tagSpan)
        }
    )
    document.body.insertBefore(liteyukiInfoDiv, document.getElementById('hardware-info'))    // 插入对象

    // 添加硬件信息
    const cpuData = hardwareData['cpu']
    const memData = hardwareData['memory']
    const swapData = hardwareData['swap']

    const cpuTagArray = [
        cpuData['name'],
        `${cpuData['cores']}${localData['cores']} ${cpuData['threads']}${localData['threads']}`,
        `${(cpuData['freq'] / 1000).toFixed(2)}GHz`
    ]

    const memTagArray = [
        `${localData['process']} ${convertSize(memData['usedProcess'])}`,
        `${localData['used']} ${convertSize(memData['used'])}`,
        `${localData['free']} ${convertSize(memData['free'])}`,
        `${localData['total']} ${convertSize(memData['total'])}`
    ]

    const swapTagArray = [
        `${localData['used']} ${convertSize(swapData['used'])}`,
        `${localData['free']} ${convertSize(swapData['free'])}`,
        `${localData['total']} ${convertSize(swapData['total'])}`
    ]
    let cpuDeviceInfoDiv = document.importNode(document.getElementById('device-info').content, true)
    let memDeviceInfoDiv = document.importNode(document.getElementById('device-info').content, true)
    let swapDeviceInfoDiv = document.importNode(document.getElementById('device-info').content, true)

    cpuDeviceInfoDiv.querySelector('.device-info').setAttribute('id', 'cpu-info')
    memDeviceInfoDiv.querySelector('.device-info').setAttribute('id', 'mem-info')
    swapDeviceInfoDiv.querySelector('.device-info').setAttribute('id', 'swap-info')
    cpuDeviceInfoDiv.querySelector('.device-chart').setAttribute('id', 'cpu-chart')
    memDeviceInfoDiv.querySelector('.device-chart').setAttribute('id', 'mem-chart')
    swapDeviceInfoDiv.querySelector('.device-chart').setAttribute('id', 'swap-chart')

    let devices = {
        'cpu': cpuDeviceInfoDiv,
        'mem': memDeviceInfoDiv,
        'swap': swapDeviceInfoDiv
    }
    // 遍历添加标签
    for (let device in devices) {
        let tagArray = []
        switch (device) {
            case 'cpu':
                tagArray = cpuTagArray
                break
            case 'mem':
                tagArray = memTagArray
                break
            case 'swap':
                tagArray = swapTagArray
                break
        }
        tagArray.forEach(
            (tag, index) => {
                let tagDiv = document.createElement('div')
                tagDiv.className = 'device-tag'
                tagDiv.innerText = tag
                // 给最后一个标签不添加后缀
                tagDiv.setAttribute('suffix', index === tagArray.length - 1 ? '0' : '1')
                devices[device].querySelector('.device-tags').appendChild(tagDiv)
            }
        )
    }


    // 插入
    document.getElementById('hardware-info').appendChild(cpuDeviceInfoDiv)
    document.getElementById('hardware-info').appendChild(memDeviceInfoDiv)
    document.getElementById('hardware-info').appendChild(swapDeviceInfoDiv)

    let cpuChart = echarts.init(document.getElementById('cpu-chart'))
    let memChart = echarts.init(document.getElementById('mem-chart'))
    let swapChart = echarts.init(document.getElementById('swap-chart'))


    cpuChart.setOption(createPieChartOption(`${localData['cpu']}\n${cpuData['percent'].toFixed(1)}%`, [
        { name: 'used', value: cpuData['percent'] },
        { name: 'free', value: 100 - cpuData['percent'] }
    ]))

    memChart.setOption(createPieChartOption(`${localData['memory']}\n${memData['percent'].toFixed(1)}%`, [
        { name: 'process', value: memData['usedProcess'] },
        { name: 'used', value: memData['used'] - memData['usedProcess'] },
        { name: 'free', value: memData['free'] }
    ]))


    swapChart.setOption(createPieChartOption(`${localData['swap']}\n${swapData['percent'].toFixed(1)}%`, [
        { name: 'used', value: swapData['used'] },
        { name: 'free', value: swapData['free'] }
    ]))


    // 磁盘信息
    const diskData = hardwareData['disk'];
    diskData.forEach((disk) => {
        let diskTitle = `${localData['free']} ${convertSize(disk['free'])}  ${localData['total']} ${convertSize(disk['total'])}`;
        let diskDiv = createBarChart(diskTitle, disk['percent'], disk['name']);

        if (disk === diskData[diskData.length - 1]) {
            diskDiv.style.marginBottom = '0';
        }
        document.getElementById('disk-info').appendChild(diskDiv);
    });
    // 随机一言
    let motto = mottos[Math.floor(Math.random() * mottos.length)]
    let mottoText = motto['text']
    let mottoFrom = `${motto['author']} ${motto['source']}`
    document.getElementById('motto-text').innerText = mottoText
    document.getElementById('motto-from').innerText = mottoFrom


}

main()
/*
// 窗口大小改变监听器 -- Debug
window.addEventListener('resize', () => {
    const diskInfos = document.querySelectorAll('.disk-info');
    diskInfos.forEach(diskInfo => {
        updateDiskNameWidth(diskInfo);
    });
});
*/