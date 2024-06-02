<script setup lang="ts">
import {ref} from 'vue'
import ItemCard from './res_item_card.vue'

// 从public/assets/resources.json加载插件
let items = ref([])
fetch('https://bot.liteyuki.icu/assets/resources.json')
  .then(response => response.json())
  .then(data => {
    items.value = data

  })
  .catch(error => console.error(error))

</script>

<template>
  <div>
    <h1>主题/资源商店</h1>
    <div class="market">
<!--      布局商品-->
      <ItemCard v-for="item in [...items].reverse()" :key="item.id" :item="item" />
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