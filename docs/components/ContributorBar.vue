<script setup lang="ts">
import {getTextRef} from "./scripts/i18n";
import {repoPath, repoURL} from "./scripts/const";

const contributorImgSrc = `https://contrib.rocks/image?repo=${repoPath}`
const contributorsUrl = `${repoURL}/graphs/contributors`
</script>

<template>
  <div class="contributor-bar">
    <h2>{{ getTextRef('thx_contributors') }}</h2>
    <a :href="contributorsUrl">
      <div class="contributor-list">
        <img :src=contributorImgSrc alt="Contributors">
      </div>
    </a>
  </div>
</template>

<style scoped>
.contributor-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
}
</style>