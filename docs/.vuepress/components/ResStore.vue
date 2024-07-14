<script setup lang="ts">
import {computed, ref} from 'vue'
import ItemCard from './ResItemCard.vue'
import * as url from "node:url";

// 从public/assets/resources.json加载插件
let filteredItems = computed(() => {
  if (!search.value) {
    return items.value.reverse()
  }
  return items.value.filter(item =>
      item.name.toLowerCase().includes(search.value.toLowerCase()) ||
      item.description.toLowerCase().includes(search.value.toLowerCase()) ||
      item.author.toLowerCase().includes(search.value.toLowerCase())
  ).reverse()
})
// 插件商店Nonebot
let items = ref([])
let search = ref('')
fetch("/assets/resources.json")
  .then(response => response.json())
  .then(data => {
    items.value = data
  })
  .catch(error => console.error(error))
// 列表倒序

</script>

<template>
  <div class="market">
    <h1>主题/资源商店</h1>
    <div class="search-box-div"><input class="item-search-box" type="text" placeholder="搜索资源" v-model="search" /></div>
    <div class="items">
      <!-- 使用filteredItems来布局商品 -->
      <ItemCard v-for="item in filteredItems" :key="item.id" :item="item"/>
    </div>
  </div>
</template>

<style scoped>
h1 {
  color: #00a6ff;
  text-align: center;
  font-weight: bold;
}

.items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
}
</style>