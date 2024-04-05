const bgs = [
    "bg1.png",
    "bg2.png",
    "bg3.png",
    "bg4.png",
    "bg5.png",
    "bg6.png",
    "bg7.png",
    "bg8.png",
    "bg9.png",
    "bg10.png",
]
// 随机选择背景图片
document.body.style.backgroundImage = `url(./img/${bgs[Math.floor(Math.random() * bgs.length)]})`;
