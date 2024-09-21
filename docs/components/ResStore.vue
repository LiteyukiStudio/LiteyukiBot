<script setup lang="ts">
import {computed, ref} from 'vue'
import ItemCard from './ResItemCard.vue'
import ResPubWindow from "./ResPubWindow.vue";
import {getTextRef, formatLang} from "./scripts/i18n";
import {RepoUrl} from "./scripts/statsApi";

import resourcesJson from "../public/resources.json"
import {useData} from "vitepress";
// formLan

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
items.value = resourcesJson
// 列表倒序

const isPublishWindowOpen = ref(false)

let newRes = ref({
  name: '',
})

function openPublishWindow() {
  isPublishWindowOpen.value = true
}

function closePublishWindow() {
  isPublishWindowOpen.value = false
}

let submitLang = ""
if (formatLang(useData().site.value.lang) === "zh") {
  submitLang = "zh"
} else {
  submitLang = "en"
}

function submitForm() {
  const title = encodeURI(`Resource: ${newRes.value.name}`)
  const issueURL = `${RepoUrl}/issues/new?assignees=&labels=Resource&template=resource_publish_${submitLang}.yml&title=${title}`
  console.log(issueURL)
  window.open(issueURL, '_blank')
}

</script>

<template>
  <div class="market">
    <h1>{{ getTextRef('resourceStore') }}</h1>
    <div class="search-box-div"><input class="item-search-box" type="text" :placeholder="getTextRef('search')"
                                       v-model="search"/></div>
    <div class="store-tabs" style="display: flex">
      <button class="store-button publish-button" @click="openPublishWindow">{{ getTextRef('publishRes') }}</button>
    </div>
    <div class="items">
      <!-- 使用filteredItems来布局商品 -->
      <ItemCard v-for="item in filteredItems" :key="item.id" :item="item"/>
    </div>
    <ResPubWindow class="pub-window" :is-visible="isPublishWindowOpen">
      <h2>{{ getTextRef("publishRes") }}</h2>
      <form @submit.prevent="submitForm">
        <label for="name">{{ getTextRef("resName") }}</label>
        <input type="text" id="name" v-model="newRes.name" :placeholder="getTextRef('resNameText')"/>
        <div class="pub-options" style="display: flex; justify-content: center">
          <button class="pub-option close" type="button" @click="closePublishWindow">{{
              getTextRef("closeButtonText")
            }}
          </button>
          <button class="pub-option submit" type="submit" @click="submitForm">{{
              getTextRef("submitButtonText")
            }}
          </button>
        </div>
      </form>
    </ResPubWindow>
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