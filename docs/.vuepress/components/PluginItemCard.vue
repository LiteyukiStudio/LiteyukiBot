<template>
  <div class="item-card">
    <div class="item-name">{{ props.item.name }}</div>
    <div class="item-description">{{ props.item.desc }}</div>
    <div class="item-bar">
      <!--      三个可点击svg，一个github，一个下载，一个可点击"https://github.com/{{ username }}.png?size=80"个人头像配上id-->
      <a :href=props.item.homepage class="btn">
        <svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 16 16">
          <path fill="currentColor"
                d="m7.775 3.275l1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0a.751.751 0 0 1 .018-1.042a.751.751 0 0 1 1.042-.018a1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018a.751.751 0 0 1-.018-1.042m-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018a.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0a.751.751 0 0 1-.018 1.042a.751.751 0 0 1-1.042.018a1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83"/>
        </svg>
      </a>

<!--      <button class="copy-btn btn"><div @click="copyToClipboard">安装</div></button> 点击后把安装命令写入剪贴板-->
      <button class="btn copy-btn" @click="copyToClipboard">复制安装命令</button>

      <div class="btn">
        <a class="author-info" :href="`https://github.com/${props.item.author }`">
          <img class="icon avatar" :src="`https://github.com/${ props.item.author }.png?size=80`" alt="">
          <div class="author-name">{{ props.item.author }}</div>
        </a>
      </div>
      <!--      复制键，复制安装命令，npm install props.item.module_name-->
    </div>
  </div>
</template>

<script setup lang="ts">
import {defineProps, onMounted} from 'vue'
import Clipboard from 'clipboard'
// 复制安装命令按钮

// 构建复制成功和失败的提示
const props = defineProps({
  item: Object
})

const copyToClipboard = () => {
  const clipboard = new Clipboard('.copy-btn', {
    text: () => `npm install ${props.item.module_name}`
  })
  clipboard.on('success', () => {
  })
  clipboard.on('error', () => {
  })
}


// 复制到剪贴板的函数
</script>

<style scoped>
.item-card {
  position: relative;
  border-radius: 15px;
  background-color: #00000011;
  height: 160px;
  padding: 16px;
  margin: 10px;
  box-sizing: border-box;
  transition: background 0.3s ease;
}

.btn {
  margin-right: 15px;
}

button {
  background-color: #00000000;
  border: none;
}

.copy-btn {
  cursor: pointer;
  color: #666;
}

.copy-btn:hover {
  color: #111;
}

.item-name {
  color: #111;
  font-size: 20px;
  margin-bottom: 10px;
}

.item-description {
  color: #333;
  font-size: 12px;
  white-space: pre-wrap;
}

.icon {
  width: 20px;
  height: 20px;
  color: $themeColor;
}

.author-info {
  display: flex;
  justify-content: left;
  align-items: center;
}

.author-name {
  font-size: 15px;
  font-weight: normal;
}

.avatar {
  border-radius: 50%;
  margin: 0 10px;
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