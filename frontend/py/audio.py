"""
GARUDAVYUHA – Tactical Aerospace Web Audio Synthesizer
Generates zero-dependency defence GCS audio feedback (beeps, radar blips, alarms)
"""

try:
    from browser import window
    IN_BROWSER = True
except ImportError:
    window = None
    IN_BROWSER = False


class TacticalAudio:
    def __init__(self):
        self.audioCtx = None
        self.isMuted = False

    def init(self):
        if not self.audioCtx and IN_BROWSER and window:
            try:
                AudioContext = getattr(window, 'AudioContext', None) or getattr(window, 'webkitAudioContext', None)
                if AudioContext:
                    self.audioCtx = AudioContext.new()
            except Exception:
                pass
        if self.audioCtx:
            try:
                if getattr(self.audioCtx, 'state', '') == 'suspended':
                    self.audioCtx.resume()
            except Exception:
                pass

    def playClick(self):
        if self.isMuted or not IN_BROWSER:
            return
        self.init()
        if not self.audioCtx:
            return

        try:
            now = self.audioCtx.currentTime
            osc = self.audioCtx.createOscillator()
            gain = self.audioCtx.createGain()
            osc.type = 'sine'
            osc.frequency.setValueAtTime(1400, now)
            osc.frequency.exponentialRampToValueAtTime(800, now + 0.04)

            gain.gain.setValueAtTime(0.08, now)
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04)

            osc.connect(gain)
            gain.connect(self.audioCtx.destination)
            osc.start()
            osc.stop(now + 0.04)
        except Exception:
            pass

    def playWarningChime(self):
        if self.isMuted or not IN_BROWSER:
            return
        self.init()
        if not self.audioCtx:
            return

        try:
            now = self.audioCtx.currentTime
            for i, freq in enumerate([880, 1174]):
                t_start = now + i * 0.1
                osc = self.audioCtx.createOscillator()
                gain = self.audioCtx.createGain()
                osc.type = 'triangle'
                osc.frequency.setValueAtTime(freq, t_start)

                gain.gain.setValueAtTime(0.12, t_start)
                gain.gain.exponentialRampToValueAtTime(0.001, t_start + 0.25)

                osc.connect(gain)
                gain.connect(self.audioCtx.destination)
                osc.start(t_start)
                osc.stop(t_start + 0.25)
        except Exception:
            pass

    def playCriticalAlarm(self):
        if self.isMuted or not IN_BROWSER:
            return
        self.init()
        if not self.audioCtx:
            return

        try:
            now = self.audioCtx.currentTime
            osc = self.audioCtx.createOscillator()
            gain = self.audioCtx.createGain()
            osc.type = 'sawtooth'
            osc.frequency.setValueAtTime(650, now)
            osc.frequency.linearRampToValueAtTime(950, now + 0.18)
            osc.frequency.linearRampToValueAtTime(650, now + 0.36)

            gain.gain.setValueAtTime(0.18, now)
            gain.gain.linearRampToValueAtTime(0.18, now + 0.3)
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.38)

            osc.connect(gain)
            gain.connect(self.audioCtx.destination)
            osc.start(now)
            osc.stop(now + 0.38)
        except Exception:
            pass

    def toggleMute(self):
        self.isMuted = not self.isMuted
        return self.isMuted


tacticalAudio = TacticalAudio()

if __name__ == '__main__':
    print("TacticalAudio module loaded successfully. Muted:", tacticalAudio.isMuted)
