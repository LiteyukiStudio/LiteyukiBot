// 数据类型声明
// import * as echarts from 'echarts';

let data = JSON.parse(document.getElementById("data").innerText)    // object
const signChartDivTemplate = document.importNode(document.getElementById("sign-chart-template").content, true)
data.forEach((item) => {
    let signChartDiv = signChartDivTemplate.cloneNode(true)
    let chartID = item["name"]
    // 初始化ECharts实例
    // 设置id
    signChartDiv.querySelector(".sign-chart").id = chartID
    document.body.appendChild(signChartDiv)

    let signChart = echarts.init(document.getElementById(chartID))

    signChart.setOption(
        {
            animation: false,
            title: {
                text: item["name"],
                textStyle: {
                    color: '#000000'  // 设置标题文本颜色为红色
                }
            },
            xAxis: {
                type: 'category',
                data: item["times"].map(timestampToTime),
            },
            yAxis: {
                type: 'value',
                min: Math.min(...item["counts"]),
            },

            series: [
                {
                    data: item["counts"],
                    type: 'line',
                }
            ]
        }
    )
})


function timestampToTime(timestamp) {
    let date = new Date(timestamp * 1000)
    let Y = date.getFullYear() + '-'
    let M = (date.getMonth() + 1 < 10 ? '0' + (date.getMonth() + 1) : date.getMonth() + 1) + '-'
    let D = date.getDate() + ' '
    let h = date.getHours() + ':'
    let m = date.getMinutes() + ':'
    let s = date.getSeconds()
    return M + D + h + m + s
}