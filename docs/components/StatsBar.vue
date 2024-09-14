<script setup lang="ts">
import DefaultTheme from "vitepress/theme";
import {ref, onMounted, onUnmounted} from "vue";
import {statsApi, GithubStats, RepoUrl, StarMapUrl, uploadVisitRecord} from "./scripts/statsApi";
import {getTextRef, updateRefData} from "./scripts/i18n";
import {onBeforeRouteUpdate} from 'vue-router';

const {Layout} = DefaultTheme;

let githubStats: GithubStats | null = null;

const dataSections = {
  total: {
    name: 'total',
    color: '#00a6ff',
    value: ref(-1),
    link: StarMapUrl
  },
  online: {
    name: 'online',
    color: '#7eff7e',
    value: ref(-1),
    link: StarMapUrl
  },
  stars: {
    name: 'stars',
    color: '#ffcc00',
    value: ref(-1),
    link: `${RepoUrl}/stargazers`
  },
  forks: {
    name: 'forks',
    color: '#ff6600',
    value: ref(-1),
    link: `${RepoUrl}/forks`
  },
  issues: {
    name: 'issues',
    color: '#ff0000',
    value: ref(-1),
    link: `${RepoUrl}/issues`
  },
  prs: {
    name: 'prs',
    color: '#f15df1',
    value: ref(-1),
    link: `${RepoUrl}/pulls`
  },
  plugins: {
    name: 'plugins',
    color: '#a766ff',
    value: ref(-1),
    link: './store/plugin'
  },
  resources: {
    name: 'resources',
    color: '#5a54fa',
    value: ref(-1),
    link: './store/resource'
  },
  visitors: {
    name: 'visitors',
    color: '#00a6ff',
    value: ref(-1),
    link: RepoUrl
  },
}

async function updateData() {
  // dataSections.online.value.value = await statsApi.getOnline();
  // dataSections.total.value.value = await statsApi.getTotal();
  [
    dataSections.online.value.value,
    dataSections.total.value.value,
    dataSections.plugins.value.value,
    dataSections.resources.value.value,
      dataSections.visitors.value.value,
    githubStats,

  ] = await Promise.all([
    statsApi.getOnline(),
    statsApi.getTotal(),
    statsApi.getPluginNum(),
    statsApi.getResourceNum(),
    statsApi.getVisitCount(),
    statsApi.getGithubStats(),
  ]);
  dataSections.stars.value.value = githubStats?.stars || 0;
  dataSections.forks.value.value = githubStats?.forks || 0;
  dataSections.issues.value.value = githubStats?.issues || 0;
  dataSections.prs.value.value = githubStats?.prs || 0;
}

function formatNumber(num: { value: number }): string {
  return num.value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}


onMounted(() => {
  const intervalId = setInterval(updateData, 10000);
  updateData();
  uploadVisitRecord();
  onUnmounted(() => {
    clearInterval(intervalId);
  });
});

onBeforeRouteUpdate(() => {
  updateRefData();
});

console.log(
    "  _      _ _                   _    _ ____        _   \n" +
    " | |    (_) |                 | |  (_)  _ \\      | |  \n" +
    " | |     _| |_ ___ _   _ _   _| | ___| |_) | ___ | |_ \n" +
    " | |    | | __/ _ \\ | | | | | | |/ / |  _ < / _ \\| __|\n" +
    " | |____| | ||  __/ |_| | |_| |   <| | |_) | (_) | |_ \n" +
    " |______|_|\\__\\___|\\__, |\\__,_|_|\\_\\_|____/ \\___/ \\__|\n" +
    "                    __/ |                             \n" +
    "                   |___/                              "
)

console.log(
    getTextRef('easterEgg')
)

</script>

<template>
  <Layout>
    <template #home-features-before>
      <div class="stats-bar-content">
        <div class="stats-bar">
          <div class="stats-info">
            <div class="stats-title">{{ getTextRef('stats') }}</div>
            <div class="sections">
              <div v-for="section in Object.values(dataSections)" :key="section.name" class="section">
                <a :href="section.link" target="_blank">
                  <div class="section-tab">
                    <span class="dot" :style="{backgroundColor: section.color}"></span>
                    <span class="text">{{ getTextRef(section.name) }}</span>
                  </div>
                  <div class="number">{{ formatNumber(section.value) }}</div>
                </a>
              </div>
            </div>
          </div>
          <div class="starmap">
            <iframe src="https://starmap.liteyuki.icu/" width="100%" height="300px" class="gamma">
            </iframe>
          </div>
        </div>
      </div>
    </template>
  </Layout>
</template>

<style scoped>

.stats-bar-content {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: column;
}

.gamma {
  filter: brightness(1.8);
}

.dark .gamma {
  filter: brightness(1.0);
}

.stats-bar {
  width: 80%;
  max-width: 1150px;
  display: flex;
  justify-content: space-between;
  padding: 20px;
  margin: 10px;
  border-radius: var(--border-radius-2);
  background-color: var(--vp-c-gray-1);
  flex-direction: column; /* 默认纵向布局 */
}

.stats-info{
  margin-bottom: 20px;
}

.stats-title {
  font-size: 20px;
  font-weight: bold;
  margin-bottom: 20px;
  text-align: center;
}

.sections {
  height: 100%;
  width: 100%;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 15px;
  margin: 10px;
}

.section {
  display: flex;
  flex-direction: column;
  position: relative; /* 使伪元素相对于父元素定位 */
  border-radius: var(--border-radius-2);
}

.section::before {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  border: 0 solid transparent; /* 初始边框为透明 */
  transition: border 0.1s ease-in-out; /* 添加过渡效果 */
  border-radius: var(--border-radius-2);
  pointer-events: none; /* 确保伪元素不会阻挡点击事件 */
}

.section:hover::before {
  border: 1px solid #00a6ff; /* 悬停时添加边框 */
  border-radius: var(--border-radius-2);
}

.section-tab {
  margin-left: 15px;
  display: flex;
  justify-content: flex-start;
  align-items: center; /* 确保垂直居中 */
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 5px;
}

.text {
  font-size: 14px;
  white-space: nowrap;
  align-items: center;
}

.number {
  font-size: 27px;
  font-weight: bold;
  margin-top: 5px;
  margin-left: 15px;
}

.starmap {
  position: relative;
  width: 100%;
  height: 200px;
  overflow: hidden;
  border-radius: var(--border-radius-2);
}

.starmap iframe {
  position: absolute;
  top: -150px; /* 根据需要调整裁剪位置 */
  left: -40px; /* 根据需要调整裁剪位置 */;
  width: calc(100% + 80px); /* 根据需要调整裁剪宽度 */
  height: calc(100% + 300px); /* 根据需要调整裁剪高度 */
}

@media (min-width: 768px) {
  /* PC模式下的样式 */
  .stats-bar {
    flex-direction: row;
    margin: 30px;
  }

  .stats-info {
    width: 40%;
    margin: 10px 30px 30px 30px;
  }

  .starmap {
    width: 60%;
    height: 400px;
  }

  .starmap iframe {
    position: absolute;
    top: -130px; /* 根据需要调整裁剪位置 */
    left: -60px; /* 根据需要调整裁剪位置 */;
    width: calc(100% + 120px); /* 根据需要调整裁剪宽度 */
    height: calc(100% + 280px); /* 根据需要调整裁剪高度 */
  }
}

</style>