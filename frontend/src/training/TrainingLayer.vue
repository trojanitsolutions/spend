<template>
	<CoachOverlay v-if="state.run?.phase === 'steps'" :key="state.run.scenario.name" />
	<FinishDialog />
	<Recorder v-if="recorder.scenario && !state.run" />
</template>

<script setup lang="ts">
import CoachOverlay from "./CoachOverlay.vue"
import FinishDialog from "./FinishDialog.vue"
import Recorder from "./Recorder.vue"
import { recorder } from "./recorder"
import { state } from "./run"
</script>
