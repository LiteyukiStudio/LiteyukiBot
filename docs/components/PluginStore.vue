<script setup lang="ts">
import {computed, ref} from 'vue'
import ItemCard from './PluginItemCard.vue'
import ToggleSwitch from "./ToggleSwitch.vue";
import {getTextRef} from "./scripts/i18n";

let showLiteyukiPluginOnly = ref(false)
let filteredItems = computed(() => {
  let filtered = items.value
  if (search.value) {
    filtered = filtered.filter(item =>
        item.name.toLowerCase().includes(search.value.toLowerCase()) ||
        item.desc.toLowerCase().includes(search.value.toLowerCase()) ||
        item.author.toLowerCase().includes(search.value.toLowerCase()) ||
        item.module_name.toLowerCase().includes(search.value.toLowerCase())
    )
  }
  if (showLiteyukiPluginOnly.value) {
    filtered = filtered.filter(item => item.is_liteyuki_plugin)
  }
  return filtered
})
// 插件商店Nonebot
let items = ref([])
let search = ref('')
// 从官方拉取
fetch("/plugins.json")
    .then(response => response.json())
    .then(data => {
      data.forEach(item => {
        item.is_liteyuki_plugin = true
      })
      items.value = data
    })
    .catch(error => console.error(error))

//追加
fetch('https://registry.nonebot.dev/plugins.json')
    .then(response => response.json())
    .then(data => {
      // 遍历data的每一项，把is_official设为false
      data.forEach(item => {
        item.is_official = false
      })
      items.value = items.value.concat(data)
    })

</script>

<template>
  <div class="market">
    <h1>{{ getTextRef('pluginStore') }}</h1>
    <p>{{ getTextRef('pluginStoreDesc') }}</p>
    <!--    搜索框-->
    <div class="search-box-div">
      <input class="item-search-box" type="text" v-model="search" :placeholder="getTextRef('search')"/>
      <ToggleSwitch v-model:modelValue="showLiteyukiPluginOnly"/>
      {{ getTextRef('liteyukiOnly') }}
    </div>
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

.search-box-div {
  display: flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 10px;
}

.search-box-div input {
  margin-right: 10px;
}
</style>