import numpy as np
from pydub import AudioSegment
import noisereduce as nr
from scipy import signal

class AudioPreprocessor:
    def __init__(self):
        self.target_sample_rate = 16000
        self.target_channels = 1

    def process_audio(self, audio_path: str) -> AudioSegment:
        """Prétraitement complet du fichier audio"""
        # Charger l'audio
        audio = AudioSegment.from_file(audio_path)
        
        # Normalisation des paramètres de base
        audio = self._normalize_audio_params(audio)
        
        # Conversion en numpy array pour le traitement avancé
        samples = np.array(audio.get_array_of_samples())
        
        # Réduction du bruit
        samples = self._reduce_noise(samples)
        
        # Normalisation du volume
        samples = self._normalize_volume(samples)
        
        # Application d'un filtre passe-bande pour la voix
        samples = self._apply_voice_filter(samples)
        
        # Reconversion en AudioSegment
        processed_audio = AudioSegment(
            samples.tobytes(), 
            frame_rate=self.target_sample_rate,
            sample_width=audio.sample_width,
            channels=self.target_channels
        )
        
        return processed_audio

    def _normalize_audio_params(self, audio: AudioSegment) -> AudioSegment:
        """Normalisation des paramètres audio de base"""
        # Conversion en mono
        if audio.channels > 1:
            audio = audio.set_channels(self.target_channels)
        
        # Normalisation du taux d'échantillonnage
        if audio.frame_rate != self.target_sample_rate:
            audio = audio.set_frame_rate(self.target_sample_rate)
        
        return audio

    def _reduce_noise(self, samples: np.ndarray) -> np.ndarray:
        """Réduction du bruit avec un seuil adaptatif"""
        # Calcul du seuil de bruit
        noise_threshold = np.percentile(