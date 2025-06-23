import numpy as np
from scipy import signal
import librosa
import noisereduce as nr
import soundfile as sf

class AudioPreprocessor:
    def __init__(self):
        self.target_sr = 16000  # Fréquence d'échantillonnage cible
        self.target_db = -25    # Niveau de volume cible en dB

    def preprocess_audio(self, audio_path: str, output_path: str = None) -> str:
        """
        Prétraite le fichier audio pour améliorer la qualité de transcription
        """
        try:
            # Charger l'audio
            y, sr = librosa.load(audio_path, sr=None)
            
            # 1. Rééchantillonnage à 16kHz
            if sr != self.target_sr:
                y = librosa.resample(y, orig_sr=sr, target_sr=self.target_sr)
                sr = self.target_sr

            # 2. Conversion en mono si stéréo
            if len(y.shape) > 1:
                y = librosa.to_mono(y)

            # 3. Réduction du bruit
            y = nr.reduce_noise(y=y, sr=sr, stationary=True, prop_decrease=0.75)

            # 4. Normalisation du volume
            y = self._normalize_audio(y)

            # 5. Amélioration de la parole
            y = self._enhance_speech(y, sr)

            # 6. Filtrage passe-bande pour la voix (300Hz-3400Hz)
            y = self._apply_bandpass_filter(y, sr)

            # Sauvegarder l'audio prétraité
            output_path = output_path or audio_path.replace('.wav', '_processed.wav')
            sf.write(output_path, y, sr)

            return output_path

        except Exception as e:
            print(f"Erreur lors du prétraitement audio: {str(e)}")
            return audio_path

    def _normalize_audio(self, y: np.ndarray) -> np.ndarray:
        """Normalise le volume audio"""
        # Calcul du RMS actuel
        rms = np.sqrt(np.mean(y**2))
        target_rms = 10 ** (self.target_db/20)
        
        # Ajuster le gain
        gain = target_rms / (rms + 1e-6)
        y_normalized = y * gain
        
        # Clip pour éviter la distorsion
        return np.clip(y_normalized, -1.0, 1.0)

    def _enhance_speech(self, y: np.ndarray, sr: int) -> np.ndarray:
        """Améliore la clarté de la parole"""
        # 1. Égalisation pour améliorer l'intelligibilité
        y_eq = self._apply_speech_eq(y, sr)
        
        # 2. Compression dynamique légère
        y_compressed = self._apply_compression(y_eq)
        
        # 3. Dé-réverbération simple
        y_clean = self._reduce_reverb(y_compressed, sr)
        
        return y_clean

    def _apply_speech_eq(self, y: np.ndarray, sr: int) -> np.ndarray:
        """Applique une égalisation optimisée pour la parole"""
        # Boost léger des fréquences de la voix (2-4kHz)
        freqs = [100, 500, 2000, 4000]
        gains = [-2, 0, 3, 4]  # dB
        
        y_eq = y.copy()
        for freq, gain in zip(freqs, gains):
            # Filtre en peigne
            b, a = signal.butter(2, freq/(sr/2), btype='bandpass')
            filtered = signal.lfilter(b, a, y)
            y_eq += filtered * (10**(gain/20) - 1)
        
        return y_eq

    def _apply_compression(self, y: np.ndarray) -> np.ndarray:
        """Applique une compression dynamique douce"""
        threshold = 0.3
        ratio = 2.0
        makeup_gain = 1.0
        
        # Calcul du gain de compression
        gain_mask = np.abs(y) > threshold
        compressed = np.copy(y)
        compressed[gain_mask] = threshold + (np.abs(y[gain_mask]) - threshold) / ratio
        compressed *= np.sign(y[gain_mask])
        
        # Application du makeup gain
        return compressed * makeup_gain

    def _reduce_reverb(self, y: np.ndarray, sr: int) -> np.ndarray:
        """Réduit la réverbération"""
        # Estimation et suppression de la réverbération
        y_reversed = np.flip(y)
        decay_factor = 0.6
        
        # Filtre simple pour réduire la réverbération
        b = [1.0, -decay_factor]
        a = [1.0]
        y_clean = signal.lfilter(b, a, y_reversed)
        return np.flip(y_clean)

    def _apply_bandpass_filter(self, y: np.ndarray, sr: int) -> np.ndarray:
        """Applique un filtre passe-bande pour la voix"""
        # Fréquences de coupure pour la voix
        low_freq = 300  # Hz
        high_freq = 3400  # Hz
        
        # Création du filtre
        nyquist = sr / 2
        b, a = signal.butter(4, [low_freq/nyquist, high_freq/nyquist], btype='bandpass')
        
        # Application du filtre
        return signal.filtfilt(b, a, y)