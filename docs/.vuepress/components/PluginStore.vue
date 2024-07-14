<script setup lang="ts">
import {computed, ref} from 'vue'
import ItemCard from './PluginItemCard.vue'


let filteredItems = computed(() => {
  if (!search.value) {
    return items.value
  }
  return items.value.filter(item =>
      item.name.toLowerCase().includes(search.value.toLowerCase()) ||
      item.desc.toLowerCase().includes(search.value.toLowerCase()) ||
      item.author.toLowerCase().includes(search.value.toLowerCase()) ||
      item.module_name.toLowerCase().includes(search.value.toLowerCase())
  )
})
// 插件商店Nonebot
let items = ref([])
let search = ref('')
// 从官方拉取
fetch("/assets/plugins.json")
    .then(response => response.json())
    .then(data => {
      items.value = data
    })
    .catch(error => console.error(error))

//追加
fetch('https://registry.nonebot.dev/plugins.json')
    .then(response => response.json())
    .then(data => {
      items.value = items.value.concat(data)
    })


</script>

<template>
  <div>
    <h1>插件商店</h1>
    <p>内容来自<a href="https://nonebot.dev/store/plugins">NoneBot插件商店</a>和轻雪商店，在此仅作引用，具体请访问NoneBot插件商店</p>
    <!--    搜索框-->
    <input class="item-search-box" type="text" placeholder="搜索插件" v-model="search"/>
    <div class="market">
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

.market {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
}
</style>