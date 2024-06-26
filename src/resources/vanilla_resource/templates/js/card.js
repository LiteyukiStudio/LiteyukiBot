const bgs = [
    "bg1.webp",
    "bg2.webp",
    "bg3.webp",
    "bg4.webp",
    "bg5.webp",
    "bg6.webp",
    "bg7.webp",
]
// 随机选择背景图片
document.body.style.backgroundImage = `url(./img/${bgs[Math.floor(Math.random() * bgs.length)]})`;
// body后插入info-box id=description
let descriptionDiv = document.createElement("div");
descriptionDiv.className = 'info-box'
descriptionDiv.id = 'author-description'
// 添加一副头像且垂直居中
let avatar = document.createElement("img");
avatar.src = 'https://q.qlogo.cn/g?b=qq&nk=2751454815&s=640'
avatar.style.height = '50px';
avatar.style.borderRadius = '50%';

let text = document.createElement("div");
text.id = 'author-text';
text.innerText = 'Designed by SnowyKami';
descriptionDiv.appendChild(avatar);
descriptionDiv.appendChild(text);
document.body.appendChild(descriptionDiv);
