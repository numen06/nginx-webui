<script setup lang="ts">
import { RouterView } from 'vue-router'
import FeedbackHost from '@/components/app/FeedbackHost.vue'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
</script>

<template>
  <TooltipProvider :delay-duration="250">
    <RouterView />
    <FeedbackHost />
    <Toaster
      theme="dark"
      position="top-right"
      :toast-options="{ class: 'border-border bg-popover text-popover-foreground' }"
    />
  </TooltipProvider>
</template>
