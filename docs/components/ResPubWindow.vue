<template>
  <div v-if="isVisible" class="floating-window">
    <div class="window-content">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import {defineProps} from 'vue'

const props = defineProps({
  isVisible: Boolean,
})
</script>

<style scoped>
.floating-window {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.window-content {
  background: var(--vp-c-gray-1);
  padding: 20px;
  border-radius: 5px;
  max-width: 60%;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}
</style>