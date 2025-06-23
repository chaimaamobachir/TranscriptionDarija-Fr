import os
import openai
import speech_recognition as sr
import tempfile
from typing import Dict
from pydub import AudioSegment
from pydub.utils import which
import time
from audio_preprocessing import AudioPreprocessor

# Configuration de l'API OpenAI
openai.api_key = "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"

# Vérifier que FFmpeg est disponible
if not which("ffmpeg"):
    print("ATTENTION: FFmpeg n'est pas installé. La conversion audio ne fonctionnera pas.")

class TranscriptionService:
    def __init__(self):
        # Vérification de la clé API
        if not openai.api_key:
            print("ERREUR: La clé API OpenAI n'est pas configurée!")
            
        # Initialisation de SpeechRecognizer
        self.recognizer = sr.Recognizer()
        
        # Ajustements pour une meilleure reconnaissance
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        
        # Configuration des langues
        self.language_config = {
            "darija": {
                "google_lang": "ar-MA"
            },
            "french": {
                "google_lang": "fr-FR"
            }
        }
        
        # Initialisation de l'AudioPreprocessor
        self.audio_preprocessor = AudioPreprocessor()
        
        self.segment_counter = 0
        self.last_transcription = None

    def convert_to_wav(self, input_path: str) -> str:
        """Convertit un fichier audio vers le format WAV compatible avec speech_recognition"""
        try:
            print(f"Conversion du fichier: {input_path}")
            
            # Détecter le format et convertir avec pydub
            try:
                # Essayer de charger comme WebM d'abord
                if input_path.endswith('.wav') and os.path.getsize(input_path) > 44:
                    # Vérifier si c'est déjà un vrai WAV
                    with open(input_path, 'rb') as f:
                        header = f.read(12)
                        if header.startswith(b'RIFF') and b'WAVE' in header:
                            print("Fichier déjà au format WAV valide")
                            return input_path
                
                # Charger avec pydub (supporte WebM, MP3, etc.)
                audio = AudioSegment.from_file(input_path)
                print(f"Audio chargé: {len(audio)}ms, {audio.frame_rate}Hz, {audio.channels} canaux")
                
                # Normaliser vers WAV 16kHz mono
                audio = audio.set_frame_rate(16000)
                audio = audio.set_channels(1)
                audio = audio.set_sample_width(2)  # 16 bits
                
                # Créer un fichier temporaire WAV
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
                    temp_wav_path = temp_wav.name
                    
                # Exporter vers WAV
                audio.export(temp_wav_path, format="wav")
                print(f"Conversion réussie vers: {temp_wav_path}")
                
                return temp_wav_path
                
            except Exception as e:
                print(f"Erreur lors de la conversion avec pydub: {str(e)}")
                # Fallback: essayer avec FFmpeg directement
                return self._convert_with_ffmpeg(input_path)
                
        except Exception as e:
            print(f"Erreur de conversion: {str(e)}")
            raise ValueError(f"Impossible de convertir le fichier audio: {str(e)}")

    def _convert_with_ffmpeg(self, input_path: str) -> str:
        """Fallback: conversion avec FFmpeg"""
        import subprocess
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
            temp_wav_path = temp_wav.name
            
        try:
            # Commande FFmpeg pour convertir vers WAV 16kHz mono
            cmd = [
                'ffmpeg', '-y',  # -y pour overwrite
                '-i', input_path,
                '-ar', '16000',  # Sample rate 16kHz
                '-ac', '1',      # Mono
                '-c:a', 'pcm_s16le',  # PCM 16-bit
                temp_wav_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"Conversion FFmpeg réussie: {temp_wav_path}")
            return temp_wav_path
            
        except subprocess.CalledProcessError as e:
            print(f"Erreur FFmpeg: {e}")
            raise ValueError("Conversion FFmpeg échouée")

    def process_audio_file(self, filepath: str) -> Dict[str, str]:
        """Transcrit un fichier audio avec vérification du contenu"""
        try:
            # Vérification du fichier
            if not os.path.exists(filepath) or os.path.getsize(filepath) < 1024:
                return {"darija": "", "french": "", "fused": ""}

            # Prétraitement audio
            processed_path = self.audio_preprocessor.preprocess_audio(filepath)
            if not processed_path or not os.path.exists(processed_path):
                return {"darija": "", "french": "", "fused": ""}

            # Conversion WAV
            wav_path = self.convert_to_wav(processed_path)
            if not wav_path or not os.path.exists(wav_path):
                return {"darija": "", "french": "", "fused": ""}

            with sr.AudioFile(wav_path) as source:
                # Configuration optimale pour la reconnaissance
                self.recognizer.dynamic_energy_threshold = True
                self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio_data = self.recognizer.record(source)

                # Vérification de l'amplitude
                if len(audio_data.frame_data) < 1024:
                    return {"darija": "", "french": "", "fused": ""}

                # Transcriptions avec vérification du contenu
                darija_transcription = self._transcribe_with_retries(audio_data, "darija")
                french_transcription = self._transcribe_with_retries(audio_data, "french")

                # Vérifier si les transcriptions ne sont pas les valeurs par défaut
                default_phrases = [
                    "اشتركوا في القناة",
                    "Merci d'avoir regardé cette vidéo",
                    "Abonnez-vous à la chaîne"
                ]

                if (not darija_transcription.strip() and not french_transcription.strip()):
                    return {"darija": "", "french": "", "fused": ""}
                    
                # Vérifier si les transcriptions sont des phrases par défaut
                if any(phrase in darija_transcription for phrase in default_phrases) or \
                   any(phrase in french_transcription for phrase in default_phrases):
                    return {"darija": "", "french": "", "fused": ""}

                # Vérifier si c'est une répétition de la dernière transcription
                current_transcription = f"{darija_transcription}|{french_transcription}"
                if self.last_transcription == current_transcription:
                    return {"darija": "", "french": "", "fused": ""}
                self.last_transcription = current_transcription

                # Fusion des transcriptions si valides
                if darija_transcription.strip() or french_transcription.strip():
                    fused = self.fuse_transcriptions(darija_transcription, french_transcription)
                    if fused.strip():
                        self.segment_counter += 1
                        return {
                            "darija": darija_transcription,
                            "french": french_transcription,
                            "fused": fused,
                            "segment_id": self.segment_counter
                        }

                return {"darija": "", "french": "", "fused": ""}

        except Exception as e:
            print(f"Erreur de traitement: {str(e)}")
            return {"darija": "", "french": "", "fused": ""}
        finally:
            # Nettoyage des fichiers temporaires
            for temp_file in [wav_path, processed_path]:
                if temp_file and temp_file != filepath and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except Exception as e:
                        print(f"Erreur nettoyage: {e}")

    def _transcribe_with_retries(self, audio_data, language: str, max_retries: int = 2) -> str:
        """Transcription avec plusieurs tentatives en cas d'échec"""
        retry_count = 0
        while retry_count <= max_retries:
            try:
                result = self._transcribe_with_google(audio_data, language)
                if result.strip():
                    return result.strip()
                
                retry_count += 1
                if retry_count <= max_retries:
                    print(f"Nouvelle tentative de transcription {language} ({retry_count}/{max_retries})...")
                    time.sleep(0.5)
                else:
                    # Essayer Whisper en dernier recours
                    if openai.api_key:
                        print(f"Tentative avec Whisper API pour {language}")
                        whisper_result = self._transcribe_with_whisper(audio_data, language)
                        if whisper_result.strip():
                            return whisper_result.strip()
            except Exception as e:
                print(f"Erreur transcription {language} (tentative {retry_count+1}): {str(e)}")
                retry_count += 1
                if retry_count <= max_retries:
                    time.sleep(0.5)
        
        return ""

    def _transcribe_with_google(self, audio_data, language: str) -> str:
        """Utilise l'API Google Speech Recognition"""
        try:
            lang_code = self.language_config[language]["google_lang"]
            from concurrent.futures import ThreadPoolExecutor, TimeoutError
            
            with ThreadPoolExecutor() as executor:
                future = executor.submit(
                    self.recognizer.recognize_google,
                    audio_data,
                    language=lang_code
                )
                try:
                    result = future.result(timeout=10)  # 10 secondes max
                    print(f"Transcription {language} réussie: {result}")
                    return result
                except TimeoutError:
                    print(f"Timeout transcription {language}")
                    raise

        except sr.UnknownValueError:
            print(f"Google Speech Recognition n'a pas pu comprendre l'audio en {language}")
            return ""
        except sr.RequestError as e:
            print(f"Erreur de requête à Google Speech Recognition en {language}; {e}")
            return ""
        except Exception as e:
            print(f"Erreur inattendue lors de la transcription {language}: {str(e)}")
            return ""

    def _transcribe_with_whisper(self, audio_data, language: str) -> str:
        """Utilise l'API OpenAI Whisper comme fallback"""
        temp_path = None
        try:
            # Sauvegarde temporaire de l'audio pour l'API Whisper
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp:
                temp_path = temp.name
                import wave
                # Préparation du fichier WAV
                with wave.open(temp_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16 bits
                    wf.setframerate(16000)
                    wf.writeframes(audio_data.frame_data)
                
                # Appel à l'API Whisper
                with open(temp_path, 'rb') as audio_file:
                    lang_code = "fr" if language == "french" else "ar"
                    response = openai.Audio.transcribe(
                        file=audio_file,
                        model="whisper-1",
                        language=lang_code
                    )
                    return response.get("text", "")
        except Exception as e:
            print(f"Erreur Whisper: {str(e)}")
            return ""
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    time.sleep(0.1)
                    os.remove(temp_path)
                except Exception as cleanup_error:
                    print(f"Erreur lors du nettoyage Whisper: {cleanup_error}")

    def fuse_transcriptions(self, darija_text: str, french_text: str) -> str:
        """Fusion intelligente des transcriptions"""
        if not darija_text.strip() and not french_text.strip():
            return ""

        try:
            if not darija_text.strip():
                return french_text.strip()
            if not french_text.strip():
                return darija_text.strip()

            prompt = f"""
            Tu es un expert en transcription médicale marocaine.
            Fusionne ces deux transcriptions en une phrase cohérente en français d'une consultation médicale :

            Transcription Darija: "{darija_text}"
            Transcription Française: "{french_text}"

            Instructions :
            - Compare les deux transcriptions et choisis la plus claire et cohérente
            - Si la transcription française ne correspond pas au contexte de la darija, ignore-la
            - Formule une phrase simple et naturelle en français en respectant le sens original
            - Ne pas ajouter de termes ou d'interprétations qui ne sont pas dans les transcriptions
            - Retourne une chaîne vide si aucune des transcriptions n'est claire ou cohérente

            Important : Utilise uniquement les mots et le sens présents dans les transcriptions, sans ajout."""

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
                timeout=5
            )

            fused_text = response.choices[0].message.content.strip()
            
            # Vérification finale du contenu
            if any(phrase in fused_text.lower() for phrase in ["abonnez-vous", "merci d'avoir", "like", "subscribe"]):
                return ""
                
            return fused_text

        except Exception as e:
            print(f"Erreur fusion: {str(e)}")
            return french_text.strip() or darija_text.strip()

    def consolidate_transcription(self, segments: list) -> str:
        """Consolide plusieurs segments de transcription en un texte cohérent."""
        if not segments:
            return ""
        
        try:
            processed_segments = []
            
            # Extraire le texte de chaque segment
            for segment in segments:
                if isinstance(segment, dict):
                    if segment.get('fused'):
                        processed_segments.append(segment['fused'])
                    elif segment.get('french'):
                        processed_segments.append(segment['french'])
                    elif segment.get('darija'):
                        processed_segments.append(segment['darija'])
                elif isinstance(segment, str):
                    processed_segments.append(segment)
            
            # Filtrer les segments vides
            non_empty_segments = [seg for seg in processed_segments if seg and isinstance(seg, str) and seg.strip()]
            
            if not non_empty_segments:
                return ""
            
            if len(non_empty_segments) == 1:
                return non_empty_segments[0]
            
            # Construire le texte pour la consolidation
            segments_text = '\n'.join(f'Segment {i+1}: "{segment.strip()}"' 
                                    for i, segment in enumerate(non_empty_segments))
            
            prompt = f"""
            Consolide ces segments de transcription en respectant leur ordre et leur sens original :

            {segments_text}

            Instructions :
            1. GARDE l'ordre chronologique des segments
            2. FUSIONNE les segments en gardant leur sens original
            3. ÉVITE les répétitions tout en conservant les informations importantes
            4. N'AJOUTE aucune information qui n'est pas dans les segments
            5. RETOURNE le texte consolidé en paragraphes si nécessaire

            Format : Texte fluide en français, respectant la chronologie des segments."""

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.3,
                max_tokens=2000
            )
            
            consolidated = response.choices[0].message.content.strip()
            return consolidated
            
        except Exception as e:
            print(f"Erreur lors de la consolidation: {str(e)}")
            # Fallback: joindre les segments avec des retours à la ligne
            return "\n".join(seg for seg in non_empty_segments if seg)

    def generate_medical_report(self, transcription: str) -> str:
        """Génère un compte rendu médical structuré à partir de la transcription."""
        if not transcription or not transcription.strip():
            return "Impossible de générer un rapport: transcription vide"
        
        try:
            prompt = f"""
            Tu es un médecin expert en rédaction de comptes rendus médicaux.
            Génère un compte rendu médical structuré et professionnel à partir de cette transcription d'une consultation:
            
            Transcription: "{transcription}"
            
            Structure obligatoire:
            - MOTIF DE CONSULTATION
            - ANTÉCÉDENTS
            - EXAMEN CLINIQUE
            - DIAGNOSTIC
            - PLAN DE TRAITEMENT
            - RECOMMANDATIONS
            
            INSTRUCTIONS IMPORTANTES:
            1. MAINTIENS uniquement les informations présentes dans la transcription
            2. N'INVENTE aucune information médicale
            3. Si une section ne peut pas être remplie faute d'informations, indique "Non précisé dans la consultation"
            4. UTILISE un français médical professionnel et adapté
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-4-turbo",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.3,
                max_tokens=2000
            )
            
            report = response.choices[0].message.content.strip()
            return report
            
        except Exception as e:
            print(f"Erreur lors de la génération du rapport: {str(e)}")
            return f"Erreur de génération du rapport: {str(e)}"