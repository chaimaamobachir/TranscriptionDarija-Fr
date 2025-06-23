import sounddevice as sd
import numpy as np
import threading
import queue
import time

class AudioProcessor:
    def __init__(self):
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.sample_rate = 16000
        self.block_duration = 5  # secondes
        self.silence_threshold = 0.008
        self.status = {
            "recording": False,
            "audio_level": 0,
            "status_message": "Prêt"
        }
        self.stream = None
        self.recording_thread = None

    def start_recording(self):
        if self.is_recording:
            return
        
        self.is_recording = True
        self.status["recording"] = True
        self.status["status_message"] = "Enregistrement en cours"
        
        block_size = int(self.sample_rate * self.block_duration)
        
        def callback(indata, frames, time, status):
            if self.is_recording:
                audio_data = indata.copy()
                rms = self.calculate_rms(audio_data)
                self.update_status(rms)
                
                if rms > self.silence_threshold:
                    self.audio_queue.put(audio_data)

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            callback=callback,
            blocksize=block_size
        )
        
        self.stream.start()
        
        self.recording_thread = threading.Thread(
            target=self._recording_monitor,
            daemon=True
        )
        self.recording_thread.start()

    def stop_recording(self):
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        self.status["recording"] = False
        self.status["status_message"] = "Enregistrement arrêté"
        self.status["audio_level"] = 0

    def get_status(self):
        return self.status

    def get_audio_queue(self):
        return self.audio_queue

    def calculate_rms(self, audio_data):
        audio_flat = audio_data.flatten()
        return np.sqrt(np.mean(np.square(audio_flat)))

    def update_status(self, rms_value):
        self.status["audio_level"] = min(100, rms_value * 5000)
        
        if rms_value > self.silence_threshold:
            self.status["status_message"] = "Parole détectée"
        else:
            self.status["status_message"] = "Silence détecté"

    def _recording_monitor(self):
        while self.is_recording:
            time.sleep(0.1)