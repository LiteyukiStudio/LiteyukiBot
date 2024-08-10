/**
 * @typedef {Object} Location
 * @property {string} city - The city name.
 * @property {string} country - The country name.
 *
 * @typedef {Object} Weather
 * @property {number} temperature - The current temperature.
 * @property {string} description - The weather description.
 *
 * @typedef {Object} Data
 * @property {Location} location - The location data.
 * @property {Weather} weather - The weather data.
 */

/** @type {Data} */

let data = JSON.parse(document.getElementById("data").innerText)

let localData = data["localization"]  // 本地化数据

let weatherNow = data["weatherNow"]

let weatherDaily = data["weatherDaily"]
let weatherHourly = data["weatherHourly"]
let aqi = data["aqi"]
let weatherAstronomy = data["weatherAstronomy"]
let is_dev = data["is_dev"]
let attr = data["attr"]


let locationData = data["location"]

// 处理aqi
let aqiValue = 0
if ("aqi" in aqi) {
    aqi["aqi"].forEach(
        (item) => {
            if (item["defaultLocalAqi"]) {
                document.getElementById("aqi-data").innerText = "AQI " + item["valueDisplay"] + " " + item["category"]
                // 将(255,255,255)这种格式的颜色设置给css
                if (is_dev) {
                    //开发版
                    document.getElementById("aqi-dot").style.backgroundColor = "rgb(" + item["color"]['red'] + "," + item["color"]['green'] + "," + item["color"]['blue'] + "," + item["color"]['alpha'] + ")"
                } else {
                    //正式版
                    document.getElementById("aqi-dot").style.backgroundColor = "rgb(" + item["color"] + ")"
                }
            }
        }
    )
} else {
    document.getElementById("aqi-dot").style.backgroundColor = '#fff'
    document.getElementById("aqi-data").innerText = localData['no_aqi']
}


templates = {
    "time": weatherNow["now"]["obsTime"],
    "city": locationData["name"],
    "adm": locationData["country"] + " " + locationData["adm1"] + " " + locationData["adm2"],
    "temperature-now": weatherNow["now"]["temp"] + "°",
    "temperature-range": weatherDaily["daily"][0]["tempMin"] + "°/" + weatherDaily["daily"][0]["tempMax"] + "°",
    "description": weatherNow["now"]["text"]
}

// 遍历每一个id，给其赋值
for (let id in templates) {
    document.getElementById(id).innerText = templates[id]
}


subtemplates = {
    "now-windDirect": weatherNow["now"]["windDir"] + " " + weatherNow["now"]["wind360"] + "°",
    "now-windVelocity": "风矢 " + weatherNow["now"]["windScale"] + "级 " + weatherNow["now"]["windSpeed"] + "km/h",
    "now-humidity": "湿度 " + weatherNow["now"]["humidity"] + "%",
    "now-feelsLike": "体感 " + weatherNow["now"]["feelsLike"] + "°C",
    "now-precip": "降水 " + weatherNow["now"]["precip"] + "mm",
    "now-pressure": "气压 " + weatherNow["now"]["pressure"] + "hPa",
    "vis": "能见 " + weatherNow["now"]["vis"] + "km",
    "cloud ": "云量 " + (weatherNow["now"]["cloud"] == "" ? "无数据" : (weatherNow["now"]["cloud"] + "%")),
    "astronomy-sunrise": "日出 " + get_time_hour(weatherAstronomy["sunrise"]),
    "astronomy-sunset": "日落 " + get_time_hour(weatherAstronomy["sunset"])
}

let subItemDivTemplate = document.importNode(document.getElementById("sub-info-template").content, true);

let subItemDiv = subItemDivTemplate.querySelector(".sub-info");

for (let id in subtemplates) {
    let element = subItemDiv.querySelector(`#${id}`);
    if (element) {
        element.innerText = subtemplates[id];
    }
}

document.getElementById('sub-info').appendChild(subItemDiv);

let maxHourlyItem = 8
let percentWidth = 1 / (maxHourlyItem * 1.5) * 100
let hourlyStep = 2 // n小时一个数据
let hourlyCount = 0

let hourlyItemDivTemplate = document.importNode(document.getElementById("hourly-item-template").content, true)
weatherHourly['hourly'].forEach(
    (item, index) => {
        if (index % hourlyStep !== 0) {
            return
        }
        if (hourlyCount >= maxHourlyItem) {
            return
        }

        let hourlyItemDiv = document.importNode(hourlyItemDivTemplate, true)
        hourlyItemDiv.className = "hourly-item"
        hourlyItemDiv.querySelector('.hourly-icon').setAttribute("src", `./img/qw_icon/${item["icon"]}.png`)
        hourlyItemDiv.querySelector('.hourly-time').innerText = get_time_hour(item["fxTime"])
        hourlyItemDiv.querySelector('.hourly-temperature').innerText = " " + item["temp"] + "°"
        // 设置最大宽度
        hourlyItemDiv.querySelector('.hourly-item').style.maxWidth = percentWidth + "%"
        hourlyItemDiv.querySelector('.hourly-icon').style.maxWidth = "100%"
        document.getElementById("hours-info").appendChild(hourlyItemDiv)
        hourlyCount++
    }
)

let maxDailyItem = 7
// 第一和第二天用today和tomorrow，后面用星期X英文小写
let daysStandard = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
let todayDay = new Date().getDay()
let days = [localData['today'], localData['tomorrow']]
for (let i = 0; i < 5; i++) {
    days.push(localData[daysStandard[(todayDay + 2 + i) % 7]])
}

let dailyItemDivTemplate = document.importNode(document.getElementById("daily-item-template").content, true)
weatherDaily['daily'].forEach(
    (item, index) => {
        if (index >= maxDailyItem) {
            return
        }
        let today = days[index]
        if (index >= 2) {
            today += `(${item["fxDate"].split("-")[1]}.${item["fxDate"].split("-")[2]})`
        }
        let dailyItemDiv = document.importNode(dailyItemDivTemplate, true)
        dailyItemDiv.querySelector('.icon-day').setAttribute("src", `./img/qw_icon/${item["iconDay"]}.png`)
        dailyItemDiv.querySelector('.icon-night').setAttribute("src", `./img/qw_icon/${item["iconNight"]}.png`)

        dailyItemDiv.querySelector('.daily-day').innerText = today

        dailyItemDiv.querySelector('.daily-weather').innerText = item["textDay"]
        dailyItemDiv.querySelector('.daily-temperature').innerText = item["tempMin"] + "°~" + item["tempMax"] + "°"

        document.getElementById('days-info').appendChild(dailyItemDiv)
    }
)

function get_time_hour(fxTime) {
    //     fxTime 2024-05-03T02:00+/-08:00'
    fxTime = fxTime.replace("-", "+")
    return fxTime.split("T")[1].split("+")[0]
}

let attrinfo = document.getElementById('attribution-info');
if (!is_dev & !attr) attrinfo.parentElement.style.display = "none"

attrinfo.innerText = is_dev ? "Weather Service Drived by QWeather" : (attr ? attr : "Weather Service Drived by QWeather")
