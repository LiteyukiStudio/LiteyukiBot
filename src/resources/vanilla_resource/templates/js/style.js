{
    // 环形图

    let cpuInfo = echarts.init(document.getElementById('cpu-chart'));
    let memInfo = echarts.init(document.getElementById('mem-chart'));
    let swapInfo = echarts.init(document.getElementById('swap-chart'));

    let data = JSON.parse(document.getElementById('data').innerText);

    let cpuData = data.cpu;
    let memData = data.mem;
    let swapData = data.swap;
    let diskData = data.disk;
    let sub_tag_data = {
        cpu: data.cpuTags,
        mem: data.memTags,
        swap: data.swapTags
    }
    for (let key in sub_tag_data) {
        let infoDiv = document.getElementById(key + '-info');
        sub_tag_data[key].forEach(tag => {
            let tagSpan = document.createElement('div');
            tagSpan.innerText = tag;
            tagSpan.className = 'chart-label';
            infoDiv.appendChild(tagSpan);
        });
    }
    cpuInfo.setOption(getPieOption(data.localization.cpu, cpuData));
    memInfo.setOption(getPieOption(data.localization.mem, memData));
    swapInfo.setOption(getPieOption(data.localization.swap, swapData));


    // 在disks-info中插入每个disk的div，用横向柱状图表示用量，每一行div显示一个disk，不加info-box
    diskData.forEach(disk => {
        let diskDiv = document.createElement('div');
        document.getElementById('disks-info').appendChild(diskDiv);
        let diskChart = document.createElement('div');
        diskChart.style.width = '100%';
        diskChart.style.height = '100px';
        diskDiv.appendChild(diskChart);
        let diskInfo = echarts.init(diskChart);
        // let diskTitle = disk.name + '  {{ FREE }} ' + disk.free + '  {{ TOTAL }} ' + disk.total;
        let diskTitle = `${disk.name}  ${data.localization.free} ${disk.free}  ${data.localization.total} ${disk.total}`;
        diskInfo.setOption(getBarOption(diskTitle, disk.percent));
    });

    let botData = data.bot;
    // 清空bot-info
    let botInfos = document.getElementsByClassName('bot-info');
    while (botInfos.length > 0) {
        botInfos[0].remove();
    }
    botData.forEach(bot => {
            // 在hardware-info前面插入一个div
            let botDiv = document.createElement('div');
            botDiv.className = 'info-box bot-info';
            // 在body内的hardware-info前面插入botDiv
            document.body.insertBefore(botDiv, document.getElementById('hardware-info'));

            let botIconBlock = document.createElement('div');
            let botIcon = document.createElement('img');
            botIcon.src = bot.icon;
            botIcon.className = 'bot-icon';
            botIconBlock.appendChild(botIcon);
            botDiv.appendChild(botIconBlock);

            let botDetail = document.createElement('div');
            let botName = document.createElement('div');
            botName.className = 'bot-name';
            botName.innerText = bot.name;
            if (bot.self) {
                // 添加颜色
                botName.style.color = '#d0e9ff';
            }
            botDetail.appendChild(botName);

            let botTags = document.createElement('div');
            botTags.className = 'bot-tag';
            botDetail.appendChild(botTags)

            bot.tags.forEach((tag, index) => {
                if (!tag) {
                    return;
                }
                let tagSpan = document.createElement('span');

                tagSpan.innerText = tag;
                tagSpan.className = 'tag';
                if (bot.self) {
                    // 添加颜色
                    tagSpan.style.color = '#a2d8f4';
                }
                botTags.appendChild(tagSpan);
                if (index === bot.tags.length - 1) {
                    tagSpan.setAttribute("suffix", "0")
                } else {
                    tagSpan.setAttribute("suffix", "1")
                }
            });

            botDiv.appendChild(botDetail);
        }
    )

    // 从/js/motto.js中读取mottos{}，随机选择一句
    let motto = mottos[Math.floor(Math.random() * mottos.length)];
    // 正文在中间，作者和来源格式为--作者 来源，在右下方
    let mottoDiv = document.getElementById('motto-info');
    let mottoText = document.createElement('div');
    mottoText.className = 'motto-text';
    mottoText.innerText = motto.text;
    mottoDiv.appendChild(mottoText);
    let mottoAuthor = document.createElement('div');
    mottoAuthor.className = 'motto-author';
    // motto.author和motto.source可能不存在为空，所以要判断
    if (!motto.author) {
        motto.author = '';
    }
    if (!motto.source) {
        motto.source = '';
    }
    mottoAuthor.innerText = `\n--${motto.author} ${motto.source}`;
    mottoAuthor.style.textAlign = 'right';
    mottoDiv.appendChild(mottoAuthor);

    function getPieUsage(data) {
        let total = 0
        let used = 0
        data.forEach(item => {
            total += item.value
            if (item.name === 'FREE') {
                used += item.value
            }
        })
        return (1 - used / total) * 100
    }


    function getPieOption(title, data) {
        return {
            animation: false,
            title: {
                text: title + '\n' + getPieUsage(data).toFixed(1) + '%',
                left: 'center',
                top: 'center',
                textStyle: {
                    //文字颜色

                    lineHeight: 36,
                    color: '#fff',
                    fontSize: 30
                }
            },
            tooltip: {
                show: true,
                trigger: "item",
                backgroundColor: "#ffffff00",
                // {a}（系列名称），{b}（数据项名称），{c}（数值）, {d}（百分比）
            },
            color: ['#a2d8f4', "#ffffff44", '#00a6ff'],
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
        };
    }

    function getBarOption(title, percent) {
        let fillet = 0
        if (percent < 5) {
            fillet = 50
        }
        // data为百分比，最大值为100
        return {
            background: '#d0e9ff',
            title: {
                text: title,
                left: '5%',
                top: 'center',
                textStyle: {
                    color: '#fff',
                    fontSize: 30
                }
            },
            tooltip: {
                show: true,
                trigger: "item",
                backgroundColor: "#ffffff",
            },
            grid: {
                left: '0',
                right: '0',
                top: '10%',
                bottom: '10%'
            },
            xAxis: {
                type: 'value',
                show: false
            },
            yAxis: {
                type: 'category',
                data: [''],
                show: false
            },
            series: [
                {
                    name: 'Used',
                    type: 'bar',
                    stack: 'total',
                    data: [percent],
                    itemStyle: {
                        normal: {
                            color: '#a2d8f4',
                            barBorderRadius: [50, 0, 0, 50]
                        }
                    },
                },
                {
                    name: 'Free',
                    type: 'bar',
                    stack: 'total',
                    data: [100 - percent],
                    itemStyle: {
                        normal: {
                            color: '#d0e9ff',
                            barBorderRadius: [fillet, 50, 50, fillet]
                        }
                    },
                }
            ]
        };
    }
}