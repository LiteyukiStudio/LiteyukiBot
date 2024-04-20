<script setup lang="ts">
import {ref} from 'vue'
import ItemCard from './plugin_item_card.vue'

// 插件商店Nonebot
let items = ref([])
fetch('https://registry.nonebot.dev/plugins.json')
    .then(response => response.json())
    .then(data => {
      items.value = data
    })
    .catch(error => console.error(error))

</script>

<template>
  <div>
    <h1>插件商店</h1>
    <p>所有内容来自<a href="https://nonebot.dev/store/plugins">NoneBot插件商店</a>，在此仅作引用，具体请访问NoneBot插件商店</p>
    <div class="market">
      <!--      布局商品-->
      <ItemCard v-for="item in items" :key="item.id" :item="item"/>
    </div>
  </div>
</template>

<style scoped>
h1 {
  color: #00a6ff;
  text-align: center;
  font-weight: bold;
}

.market {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
}
</style>