echart = require('echarts');
let chart = echarts.init(document.getElementById('main-chart'));
const color = ['#9ae5fc', '#dcbf71']; // 自定义图中要用到的颜色
console.log("加载图标");
// 在地图加载完成后设置所有地区不可选
function setAllRegionsUnselectable(geoModel) {
    const regions = geoModel.get('regions');

    // 遍历所有地区并设置selected为false
    for (let i = 0; i < regions.length; i++) {
        const region = regions[i];
        region.selected = false;
    }

    // 更新模型以反映更改
    geoModel.set('regions', regions);

    // 更新图表以显示更改
    chart.setOption({
        geo: {
            regions: regions
        }
    });
}

// 获取数据并初始化图表
fetch('https://api.liteyuki.icu/distribution')
    .then(response => response.json())
    .then(data => {
        // 构造 ECharts 需要的数据格式
        const locations = data.locations;
        const seriesData = locations.map(location => ({
            value: [location[1], location[0]] // 直接使用经纬度数组
        }));
        console.log(seriesData);
        // 初始化图表选项
        chart.setOption({
            backgroundColor: '#454545',
            title: {
                text: 'LiteyukiBot分布demo',
                subtext: 'LiteyukiBot分布',
                textStyle: {
                    color: '#fff',
                    fontSize: 20
                },
                top: '10px',
                left: '10px'
            },
            geo: {
                map: 'world',
                roam: false,
                itemStyle: {
                    normal: {
                        areaColor: '#000',
                        borderType: null, // 设置边界线类型为无
                        borderColor: '#000', // 设置边界线颜色

                    },
                    emphasis: {
                        areaColor: '#000',
                        borderType: null, // 设置边界线类型为无
                        borderColor: '#000', // 设置边界线颜色
                    }
                },
                regions: [] // 先保留为空
            },
            series: [{
                // 散点效果
                type: 'scatter',
                coordinateSystem: 'geo', // 表示使用的坐标系为地理坐标系
                symbolSize: 5, // 设置散点的大小为20
                itemStyle: {
                    color: '#ffeb3b', // 黄色
                },
                data: seriesData
            }],
            textStyle: {
                fontSize: 1
            }
        });

        // 在地图加载完成后设置所有地区不可选
        chart.on('ready', function () {
            const geoModel = chart.getModel().componentModels.geo[0];
            setAllRegionsUnselectable(geoModel);
        });

        // 自适应窗口大小变化
        window.addEventListener("resize", function () {
            chart.resize();
        });
    })
    .catch(error => console.error('Error fetching data:', error));