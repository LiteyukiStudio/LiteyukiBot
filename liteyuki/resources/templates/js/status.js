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
                fontSize: 30
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

/**
 * 创建磁盘用量柱状图
 * @param title
 * @param percent 数据
 */
function createBarChartOption(title, percent) {
    // percent为百分比，最大值为100
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
            console.log(botInfoDiv.querySelector('.bot-icon-img'))
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
    console.log(liteyukiData)
    let tagArray = [
        `Liteyuki ${liteyukiData['version']}`,
        `Nonebot ${liteyukiData['nonebot']}`,
        liteyukiData['python'],
        liteyukiData['system'],
        `${localData['plugins']} ${liteyukiData['plugins']}`,
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
}

main()