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
  <div class="online-status-bar">
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
</template>

<style scoped>
.online-status-bar {
  display: flex;
  justify-content: center;
  padding: 20px;
  margin: 30px 10px 10px;
  border-radius: 20px;
  background-color: var(--vp-c-gray-1);
}

.section:not(:last-child) {
  margin-right: 100px;
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

.number {
  font-size: 30px;
  font-weight: bold;
  margin-top: 5px;
}
</style>