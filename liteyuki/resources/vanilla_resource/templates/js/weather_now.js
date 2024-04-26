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

let weatherNow = data["weatherNow"]

let weatherDaily = data["weatherDaily"]
let weatherHourly = data["weatherHourly"]
let aqi = data["aqi"]

let locationData = data["location"]

// set info
// document.getElementById("time").innerText = weatherNow["now"]["obsTime"]
// document.getElementById("city").innerText = locationData["name"]
// document.getElementById("adm").innerText = locationData["country"] + " " + locationData["adm1"] + " " + locationData["adm2"]
// document.getElementById("temperature-now").innerText = weatherNow["now"]["temp"] + "°"
// document.getElementById("temperature-range").innerText = weatherNow["now"]["feelsLike"] + "°"
// document.getElementById("description").innerText = weatherNow["now"]["text"]
// 处理aqi
let aqiValue = 0
aqi["aqi"].forEach(
    (item) => {
        if (item["defaultLocalAqi"]) {
            document.getElementById("aqi-data").innerText = "AQI " + item["valueDisplay"] + " " + item["category"]
            // 将(255,255,255)这种格式的颜色设置给css
            document.getElementById("aqi-dot").style.backgroundColor = "rgb(" + item["color"] + ")"
        }
    }
)

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