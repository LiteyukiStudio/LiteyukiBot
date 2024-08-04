---
title: 地理分布
icon: globe
order: 1
category: 其他

---

:::echarts Liteyuki Dist

```js
const option = {
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
    }],
    textStyle: {
        fontSize: 1
    }
};
```