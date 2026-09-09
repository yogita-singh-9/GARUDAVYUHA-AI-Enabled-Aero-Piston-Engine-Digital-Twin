"""
GARUDAVYUHA – SIH 2026 Judge Demonstration Controller
Orchestrates the progressive 11-step presentation flow with synchronized telemetry and 3D visual twin
"""

try:
    from browser import timer
    IN_BROWSER = True
except ImportError:
    timer = None
    IN_BROWSER = False

from config import DEMO_STEPS
from telemetryEngine import telemetryEngine


class DemoController:
    def __init__(self, twin3D=None, onStepChanged=None):
        self.twin3D = twin3D
        self.onStepChanged = onStepChanged

        self.currentStepIndex = 1
        self.totalSteps = len(DEMO_STEPS)
        self.isAutoPlaying = False
        self.stepDurationSec = 6  # 6 seconds per step during auto-play
        self.remainingSeconds = self.stepDurationSec
        self.timerInterval = None

    def getCurrentStep(self):
        return DEMO_STEPS[self.currentStepIndex - 1]

    def goToStep(self, step_number):
        if step_number < 1 or step_number > self.totalSteps:
            return
        self.currentStepIndex = step_number
        self.applyStep(self.getCurrentStep())

    def nextStep(self):
        if self.currentStepIndex < self.totalSteps:
            self.goToStep(self.currentStepIndex + 1)
        else:
            self.stopAutoPlay()

    def prevStep(self):
        if self.currentStepIndex > 1:
            self.goToStep(self.currentStepIndex - 1)

    def reset(self):
        self.stopAutoPlay()
        self.currentStepIndex = 1
        telemetryEngine.resetToHealthy()
        if self.twin3D:
            try:
                self.twin3D.resetMeshHighlights()
                self.twin3D.setCameraPreset('default')
            except Exception as e:
                print("Error resetting twin in demo:", e)
        self.applyStep(self.getCurrentStep())

    def applyStep(self, step):
        step_num = step.get("step", 1)
        telemetryEngine.setDemoStep(step_num)

        if self.twin3D:
            try:
                if step_num == 1:
                    self.twin3D.resetMeshHighlights()
                elif 2 <= step_num <= 5:
                    self.twin3D.highlightSubsystem('fuel_system', 'degrading', False)
                elif step_num in (6, 7):
                    self.twin3D.highlightSubsystem('fuel_system', 'degrading', True)
                elif step_num >= 8:
                    self.twin3D.highlightSubsystem('fuel_system', 'critical', True)
            except Exception as e:
                print("Error setting twin highlights:", e)

        if self.onStepChanged:
            try:
                self.onStepChanged(step, self.currentStepIndex, self.totalSteps, self.remainingSeconds)
            except Exception as e:
                print("Error in onStepChanged:", e)

    def startAutoPlay(self):
        if self.isAutoPlaying:
            return
        self.isAutoPlaying = True
        self.remainingSeconds = self.stepDurationSec

        def on_tick():
            self.remainingSeconds -= 1
            if self.remainingSeconds <= 0:
                self.remainingSeconds = self.stepDurationSec
                if self.currentStepIndex >= self.totalSteps:
                    self.stopAutoPlay()
                else:
                    self.nextStep()

            if self.onStepChanged:
                try:
                    self.onStepChanged(self.getCurrentStep(), self.currentStepIndex, self.totalSteps, self.remainingSeconds)
                except Exception as e:
                    print("Error updating demo bar:", e)

        if IN_BROWSER and timer:
            self.timerInterval = timer.set_interval(on_tick, 1000)

    def stopAutoPlay(self):
        self.isAutoPlaying = False
        if IN_BROWSER and timer and self.timerInterval:
            timer.clear_interval(self.timerInterval)
            self.timerInterval = None

    def toggleAutoPlay(self):
        if self.isAutoPlaying:
            self.stopAutoPlay()
        else:
            self.startAutoPlay()


if __name__ == "__main__":
    demo = DemoController()
    s1 = demo.getCurrentStep()
    print(f"Step 1: {s1['title']} ({s1['badge']})")
    demo.nextStep()
    s2 = demo.getCurrentStep()
    print(f"Step 2: {s2['title']} ({s2['badge']})")
    print("DemoController test passed!")
