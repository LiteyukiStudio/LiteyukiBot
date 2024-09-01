<script setup lang="ts">
import DefaultTheme from "vitepress/theme";
import {ref, onMounted, onUnmounted} from "vue";
import {statsApi, GithubStats} from "./scripts/statsApi";
import {getTextRef, updateRef} from "./scripts/i18n";


const {Layout} = DefaultTheme;

let githubStats: GithubStats | null = null;

const dataSections = {
  total: {
    name: 'total',
    color: '#00a6ff',
    value: ref(0),
  },
  online: {
    name: 'online',
    color: '#00ff00',
    value: ref(0),
  },
  stars: {
    name: 'stars',
    color: '#ffcc00',
    value: ref(0),
  },
  forks: {
    name: 'forks',
    color: '#ff6600',
    value: ref(0),
  },
  issues: {
    name: 'issues',
    color: '#ff0000',
    value: ref(0),
  },
  prs: {
    name: 'prs',
    color: '#ff00ff',
    value: ref(0),
  },
}

async function updateData() {
  // dataSections.online.value.value = await statsApi.getOnline();
  // dataSections.total.value.value = await statsApi.getTotal();
  [
    dataSections.online.value.value,
    dataSections.total.value.value,
    githubStats,
  ] = await Promise.all([
    statsApi.getOnline(),
    statsApi.getTotal(),
    statsApi.getGithubStats(),
  ]);
  dataSections.stars.value.value = githubStats?.stars || 0;
  dataSections.forks.value.value = githubStats?.forks || 0;
  dataSections.issues.value.value = githubStats?.issues || 0;
  dataSections.prs.value.value = githubStats?.prs || 0;
}

onMounted(() => {
  const intervalId = setInterval(updateData, 10000);
  updateData();
  onUnmounted(() => {
    clearInterval(intervalId);
  });
});

</script>

<template>
  <Layout>
    <template #home-features-before>
      <div class="stats-bar-content">
        <div class="stats-bar">
          <div class="stats-info">
            <div v-for="section in Object.values(dataSections)" :key="section.name" class="section">
              <div class="section-tab">
                <span class="dot" :style="{backgroundColor: section.color}"></span>
                <span class="text">{{ getTextRef(section.name) }}</span>
              </div>
              <div class="number">{{ section.value.value }}</div>
            </div>
          </div>
          <div class="starmap">
            <iframe src="https://starmap.liteyuki.icu/" width="100%" height="300px"></iframe>
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

.stats-bar {
  width: 80%;
  max-width: 1150px;
  display: flex;
  justify-content: space-between;
  padding: 20px;
  margin: 30px;
  border-radius: var(--border-radius-2);
  background-color: var(--vp-c-gray-1);
  flex-direction: column; /* 默认纵向布局 */
}

.stats-info {
  width: 100%;
  padding: 10px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
  margin: 20px;
}

.section {
  display: flex;
  flex-direction: column;
}

.section-tab {
  margin-left: 20px;
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
  font-size: 30px;
  font-weight: bold;
  margin-top: 5px;
  margin-left: 20px;
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
  }

  .stats-info {
    width: 40%;
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