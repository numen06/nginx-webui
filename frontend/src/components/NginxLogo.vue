<template>
  <div class="nginx-logo" :class="{ 'logo-small': small, 'logo-large': large }">
    <svg
      viewBox="0 0 180 50"
      xmlns="http://www.w3.org/2000/svg"
      class="logo-svg"
    >
      <!-- Nginx 风格的字母 N - 更现代的设计 -->
      <path
        d="M 8 8 L 8 42 L 16 42 L 16 22 L 28 42 L 36 42 L 24 22 L 24 8 Z"
        fill="var(--nginx-green)"
        class="logo-letter"
      />
      <!-- 装饰性圆点 -->
      <circle
        cx="42"
        cy="25"
        r="3"
        fill="var(--nginx-green)"
        opacity="0.6"
        class="logo-dot"
      />
      <!-- WebUI 文字 -->
      <text
        x="52"
        y="32"
        font-family="'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
        font-size="20"
        font-weight="600"
        fill="var(--nginx-green)"
        class="logo-text"
        letter-spacing="1"
      >
        WebUI
      </text>
    </svg>
  </div>
</template>

<script setup>
defineProps({
  small: {
    type: Boolean,
    default: false
  },
  large: {
    type: Boolean,
    default: false
  }
})
</script>

<style scoped>
.nginx-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.logo-svg {
  width: 100%;
  height: 100%;
  filter: drop-shadow(0 0 8px var(--nginx-green-glow));
}

.logo-letter {
  animation: logoGlow 2s ease-in-out infinite alternate;
}

.logo-text {
  filter: drop-shadow(0 0 4px var(--nginx-green-glow));
}

.logo-small .logo-svg {
  width: 140px;
  height: 40px;
}

.logo-large .logo-svg {
  width: 220px;
  height: 65px;
}

.logo-dot {
  animation: logoPulse 2s ease-in-out infinite;
}

@keyframes logoPulse {
  0%, 100% {
    opacity: 0.6;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.2);
  }
}

@keyframes logoGlow {
  from {
    filter: drop-shadow(0 0 4px var(--nginx-green-glow));
  }
  to {
    filter: drop-shadow(0 0 12px var(--nginx-green-glow));
  }
}
</style>

