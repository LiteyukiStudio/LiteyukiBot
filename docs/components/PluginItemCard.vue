<template>
  <div class="item-card">
    <div class="item-name">{{ props.item.name }}</div>
    <div class="item-description">{{ props.item.desc }}</div>
    <div class="tags">
      <span class="tag" v-for="tag in props.item.tags" :key="tag" :style=getTagStyle(tag.color)>{{ tag.label }}</span>
    </div>
    <div class="item-bar">
      <!--      三个可点击svg，一个github，一个下载，一个可点击"https://github.com/{{ username }}.png?size=80"个人头像配上id-->
      <a :href=props.item.homepage class="btn" target="_blank">
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

const getTagStyle = (backgroundColor: string) => {
  // 将颜色值转换为 RGB 格式
  const rgb = backgroundColor.replace(/^#/, '');
  const [r, g, b] = rgb.match(/.{2}/g).map(x => parseInt(x, 16));

  // 计算亮度
  const brightness = (r * 299 + g * 587 + b * 114) / 1000;

  // 根据亮度决定文字颜色
  return {
    backgroundColor: backgroundColor,
    color: brightness > 128 ? '#000' : '#fff'
  };
};


// 复制到剪贴板的函数
</script>

<style scoped>
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

.icon {
  width: 20px;
  height: 20px;
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

.tag {
  display: inline-block;
  padding: 0 5px;
  margin-right: 5px;
  border-radius: 5px;
  font-size: 12px;
}
</style>