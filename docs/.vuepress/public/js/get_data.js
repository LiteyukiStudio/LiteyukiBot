
function updatePageData() {
  fetch("https://api.liteyuki.icu/count")
    .then(res => res.json())
    .then(data => {
      let total = document.getElementById("total");
      if(total !== null) {
        total.innerText = data.register;
      }
    })
    .catch(err => console.error(err));

  fetch("https://api.liteyuki.icu/online")
    .then(res => res.json())
    .then(data => {
        let online = document.getElementById("online");
        if(online !== null) {
            online.innerText = data.online;
        }
    })
    .catch(err => console.error(err));
}

updatePageData();
setInterval(() => {
  updatePageData();
}, 1000);