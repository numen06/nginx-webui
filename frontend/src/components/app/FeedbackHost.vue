<script setup lang="ts">
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Input } from '@/components/ui/input'
import {
  feedbackDialog,
  rejectFeedbackDialog,
  resolveFeedbackDialog,
} from '@/lib/feedback'

function onOpenChange(open: boolean) {
  if (!open && feedbackDialog.open) rejectFeedbackDialog()
}
</script>

<template>
  <AlertDialog :open="feedbackDialog.open" @update:open="onOpenChange">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{{ feedbackDialog.title }}</AlertDialogTitle>
        <AlertDialogDescription class="whitespace-pre-wrap">
          {{ feedbackDialog.message }}
        </AlertDialogDescription>
      </AlertDialogHeader>
      <Input
        v-if="feedbackDialog.kind === 'prompt'"
        v-model="feedbackDialog.value"
        :placeholder="feedbackDialog.inputPlaceholder"
        autofocus
        @keydown.enter.prevent="resolveFeedbackDialog"
      />
      <AlertDialogFooter>
        <AlertDialogCancel
          v-if="feedbackDialog.kind !== 'alert'"
          @click="rejectFeedbackDialog"
        >
          {{ feedbackDialog.cancelText }}
        </AlertDialogCancel>
        <AlertDialogAction @click="resolveFeedbackDialog">
          {{ feedbackDialog.confirmText }}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
