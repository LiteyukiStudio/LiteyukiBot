let server_addr = "mc.liteyuki.icu";
let api_url = "https://api.mcstatus.io/v2/status/java/" + server_addr;

let server_status = document.getElementById("now-online");

fetch(api_url)
    .then(response => {
        console.log(response);
        return response.json();
    })
    .then(data => {

        if (data.online){
            server_status.textContent = "当前状态: 在线 " + data.players.online + " / " +data.players.max;
        } else {
            server_status.textContent = "当前状态: 服务器离线";
        }
    }
)
