<script setup>
import getText from "../components/scripts/i18nData.ts";
import {ref} from "vue";

const onlineText = getText('online');
const totalText = getText('total')

const onlineFetchUrl = "https://api.liteyuki.icu/online"
const totalFetchUrl = "https://api.liteyuki.icu/count"

let online = ref(-1);
let total = ref(-1);

async function updateData() {
  try {
    const onlineResponse = await fetch(onlineFetchUrl);
    const onlineData = await onlineResponse.json();
    online.value = onlineData.online;

    const totalResponse = await fetch(totalFetchUrl);
    const totalData = await totalResponse.json();
    total.value = totalData.register;
  } catch (error) {
    console.error('Error fetching data:', error);
  }
}

updateData();
setInterval(updateData, 10000);

</script>

<template>
  <div class="stats-bar">
    <div class="stats-info">
      <div id="total" class="section">
        <div class="line">
          <span class=dot style="background-color: #00a6ff"></span>
          <span class="text">{{ totalText }}</span>
        </div>
        <div class="number">{{ total }}</div>
      </div>
      <div id="online" class="section">
        <div class="line">
          <span class=dot style="background-color: #00ff00"></span>
          <span class="text">{{ onlineText }}</span>
        </div>
        <div class="number">{{ online }}</div>
      </div>
    </div>
    <div class="starmap">
      <iframe src="https://starmap.liteyuki.icu/" width="100%" height="300px"></iframe>
    </div>
  </div>

</template>

<style scoped>

.stats-bar {
  display: flex;
  justify-content: space-between;
  padding: 20px;
  margin: 30px 10px 10px 10px;
  border-radius: var(--border-radius-2);
  background-color: var(--vp-c-gray-1);
  flex-direction: column; /* 默认纵向布局 */
}

.stats-info {
  width: 100%;
  padding: 10px;
  display: flex;
  justify-content: space-evenly;
  margin-bottom: 20px;
}

.section {
  display: flex;
  flex-direction: column;
}

.section:not(:last-child) {
  margin-right: 50px;
}

.line {
  margin-bottom: 20px;
}

.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 5px;
}

.text {
  font-size: 14px;
}

.number {
  font-size: 30px;
  font-weight: bold;
  margin-top: 5px;
}

.starmap {
  position: relative;
  width: 100%;
  height: 200px;
  overflow: hidden;
  border-radius: var(--border-radius-2);
}

.starmap iframe {
  position: absolute;
  top: -150px; /* 根据需要调整裁剪位置 */
  left: -40px; /* 根据需要调整裁剪位置 */;
  width: calc(100% + 80px); /* 根据需要调整裁剪宽度 */
  height: calc(100% + 300px); /* 根据需要调整裁剪高度 */
}

@media (min-width: 768px) {
  /* PC模式下的样式 */
  .stats-bar {
    flex-direction: row;
  }

  .stats-info {
    width: 40%;
  }

  .starmap {
    width: 60%;
    height: 400px;
  }

  .starmap iframe {
    position: absolute;
    top: -130px; /* 根据需要调整裁剪位置 */
    left: -60px; /* 根据需要调整裁剪位置 */;
    width: calc(100% + 120px); /* 根据需要调整裁剪宽度 */
    height: calc(100% + 280px); /* 根据需要调整裁剪高度 */
  }
}

</style>