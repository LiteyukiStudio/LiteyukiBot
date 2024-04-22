const data = JSON.parse(document.getElementById('data').innerText);
const bot_data = data['bot'];  // 机器人数据
const hardware_data = data['hardware'];    // 硬件数据
const liteyuki_data = data['liteyuki'];   // LiteYuki数据
const local_data = data['localization'];    // 本地化语言数据

console.log(data)

/**
 * 创建饼图
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
 * 创建柱状图
 * @param title
 * @param percent 数据
 */
function createBarChartOption(title, percent) {
    // percent为百分比，最大值为100
}

// 主函数
function main() {
    bot_data['bots'].forEach(
        (bot, index) => {
            let botInfoDiv = document.importNode(document.getElementById('bot-template').content, true)
            document.body.insertBefore(botInfoDiv, document.getElementById('hardware-info'))
            botInfoDiv.className = 'info-box bot-info'
        }
    )
}

main()