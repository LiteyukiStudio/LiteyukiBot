let data = JSON.parse(document.getElementById("data").innerText)    // object

const rowDiv = document.importNode(document.getElementById("row-template").content, true)

function randomHideChar(str) {
    // 随机隐藏6位以上字符串的中间连续四位字符，用*代替
    if (str.length <= 6) {
        return str
    }
    let start = Math.floor(str.length / 2) - 2
    return str.slice(0, start) + "****" + str.slice(start + 4)
}
data["ranking"].forEach((item) => {
    let row = rowDiv.cloneNode(true)
    let rowID = item["name"]
    let rowIconSrc = item["icon"]
    let rowCount = item["count"]

    row.querySelector(".row-name").innerText = randomHideChar(rowID)
    row.querySelector(".row-icon").src = rowIconSrc
    row.querySelector(".row-count").innerText = rowCount

    document.body.appendChild(row)
})

