const bgs = [
    "bg1.png",
    "bg3.png",
    "bg4.png",
    "bg5.png",
    "bg6.png",
    "bg7.png",
    "bg9.png",
]
// 随机选择背景图片
document.body.style.backgroundImage = `url(./img/${bgs[Math.floor(Math.random() * bgs.length)]})`;