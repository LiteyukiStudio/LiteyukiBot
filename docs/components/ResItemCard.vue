<template>
  <div class="item-card">
    <div class="item-name">{{ props.item.name }}</div>
    <div class="item-description">{{ props.item.description }}</div>
    <div class="item-bar">
      <!--      三个可点击svg，一个github，一个下载，一个可点击"https://github.com/{{ username }}.png?size=80"个人头像配上id-->
      <a :href=props.item.link class="" target="_blank">
        <svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 16 16">
          <path fill="currentColor"
                d="m7.775 3.275l1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0a.751.751 0 0 1 .018-1.042a.751.751 0 0 1 1.042-.018a1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018a.751.751 0 0 1-.018-1.042m-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018a.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0a.751.751 0 0 1-.018 1.042a.751.751 0 0 1-1.042.018a1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83"/>
        </svg>
      </a>
      <div><a class="author-info" :href="`https://github.com/${props.item.author }`">
        <img class="icon avatar" :src="`https://github.com/${ props.item.author }.png?size=80`" alt="">
        <div class="author-name">{{ props.item.author }}</div>
      </a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {defineProps} from 'vue'

const props = defineProps({
  item: Object
})
</script>

<style scoped>



.icon {
  width: 20px;
  height: 20px;
  color: $themeColor;
}





.item-bar {
  position: absolute;
  bottom: 0;
  height: 50px;
  display: flex;
  align-items: center;
  box-sizing: border-box;
  justify-content: space-between;
  color: #00000055;
}
</style>