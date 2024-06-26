function applyStyle() {
    let lineNumbers = document.body.querySelectorAll('[class^="language-"].line-numbers-mode')
    lineNumbers.forEach((item) => {
        // 插入现成的html文本
        let title = item.getAttribute('data-title')
        let tabStr =
            "<div class='tab' style='display: flex; background-color: #d0e9ff'>" +
            "   <div class='tab-buttons'>" +
            "       <div class='tab-button' style='background-color: #FF5F57'></div>" +
            "       <div class='tab-button' style='background-color: #FFBD2E'></div>" +
            "       <div class='tab-button' style='background-color: #27C93F'></div>" +
            "   </div>" +
            `   <div class='tab-title'>${title}</div>` +
            "   <div style='flex: 1'></div>" +
            "</div>"
        // 在代码块前插入选项卡
        item.insertAdjacentHTML('beforebegin', tabStr);
    })
}


applyStyle()