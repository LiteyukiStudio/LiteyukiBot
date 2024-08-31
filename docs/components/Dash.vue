<script setup lang="ts">
import {ref} from "vue";

let total = ref(0);
let online = ref(0);
fetch("https://api.liteyuki.icu/count")
    .then(res => res.json())
    .then(data => {
      total.value = data.register;
    })
    .catch(err => console.error(err));
fetch("https://api.liteyuki.icu/online")
    .then(res => res.json())
    .then(data => {
      online.value = data.online;
    })
    .catch(err => console.error(err));
</script>

<template>
  <div class="info-box">
    <h1>Dashboard</h1>
    <div class="info">
      <div class="info-item">
        <h2>Total</h2>
        <p>{{ total }}</p>
      </div>
      <div class="info-item">
        <h2>Online</h2>
        <p>{{ online }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>

</style>