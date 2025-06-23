from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from audio_processor import AudioProcessor
from transcription_service import TranscriptionService
import os
import openai  # Ajoutez cette ligne
from datetime import datetime
import tempfile

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialisation des services
audio_processor = AudioProcessor()
transcription_service = TranscriptionService()

# Après l'import de openai
openai.api_key = "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"

@app.route('/api/transcribe/start', methods=['POST'])
def start_recording():
    try:
        audio_processor.start_recording()
        return jsonify({"status": "success", "message": "Enregistrement démarré"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/transcribe/stop', methods=['POST'])
def stop_recording():
    try:
        audio_processor.stop_recording()
        return jsonify({"status": "success", "message": "Enregistrement arrêté"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/transcribe/status', methods=['GET'])
def get_status():
    return jsonify(audio_processor.get_status())

@app.route('/api/transcribe/process', methods=['POST'])
def process_audio():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Aucun fichier envoyé"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Aucun fichier sélectionné"}), 400
    
    # Sauvegarde temporaire du fichier
    filename = f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    try:
        # Assurez-vous que le dossier existe
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Sauvegarder le fichier
        file.save(filepath)
        
        # Vérifier que le fichier a bien été enregistré et qu'il est lisible
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return jsonify({"status": "error", "message": "Échec d'enregistrement du fichier audio"}), 500
        
        app.logger.info(f"Fichier sauvegardé: {filepath}, taille: {os.path.getsize(filepath)} bytes")
        
        # Traitement du fichier audio
        result = transcription_service.process_audio_file(filepath)
        
        # Debugging - Vérifier le contenu de result
        app.logger.debug(f"Résultat transcription: {result}")
        
        # S'assurer que les clés existent et ne sont pas None
        if result:
            for key in ['darija', 'french', 'fused']:
                if key not in result:
                    result[key] = ""
        
        return jsonify({"status": "success", "data": result})
    except Exception as e:
        app.logger.error(f"Erreur lors du traitement audio: {str(e)}")
        import traceback
        traceback.print_exc()  # Imprimer la stack trace complète
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        # Suppression du fichier temporaire
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            app.logger.warning(f"Échec de suppression du fichier temporaire: {str(e)}")

@app.route('/api/transcription/consolidate', methods=['POST'])
def consolidate_transcription():
    data = request.get_json()
    if not data or 'segments' not in data:
        return jsonify({"status": "error", "message": "Segments manquants"}), 400
    
    try:
        consolidated = transcription_service.consolidate_transcription(data['segments'])
        return jsonify({"status": "success", "data": consolidated})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/report/generate', methods=['POST'])
def generate_report():
    data = request.get_json()
    if not data or 'transcription' not in data:
        return jsonify({"status": "error", "message": "Transcription manquante"}), 400
    
    try:
        report = transcription_service.generate_medical_report(data['transcription'])
        return jsonify({"status": "success", "data": report})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/transcription/save', methods=['POST'])
def save_transcription():
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"status": "error", "message": "Texte manquant"}), 400
    
    try:
        filename = f"transcription_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(data['text'])
        
        return jsonify({
            "status": "success",
            "data": {
                "filename": filename,
                "path": filepath
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/test-transcription', methods=['POST'])
def test_transcription():
    """Endpoint de diagnostic pour tester la transcription"""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Aucun fichier envoyé"}), 400
    
    file = request.files['file']
    
    try:
        # Sauvegarde temporaire du fichier
        filename = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Vérification des métadonnées du fichier
        import wave
        try:
            with wave.open(filepath, 'rb') as wf:
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                frame_rate = wf.getframerate()
                frames = wf.getnframes()
                
                file_info = {
                    "filename": filename,
                    "filesize": os.path.getsize(filepath),
                    "channels": channels,
                    "sample_width": sample_width,
                    "frame_rate": frame_rate,
                    "frames": frames,
                    "duration": frames / frame_rate if frame_rate > 0 else 0
                }
        except Exception as wave_error:
            file_info = {
                "filename": filename,
                "filesize": os.path.getsize(filepath),
                "error": str(wave_error)
            }
        
        return jsonify({
            "status": "success", 
            "message": "Fichier audio reçu",
            "file_info": file_info
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/debug/test-transcription', methods=['GET'])
def debug_transcription():
    """Endpoint de test pour vérifier la transcription"""
    test_data = {
        "darija": "مرحبا، كيفاش نقدر نساعدك؟",
        "french": "Bonjour, comment puis-je vous aider ?",
        "fused": "Bonjour, comment puis-je vous aider ?"
    }
    
    return jsonify({"status": "success", "data": test_data})

# Servir le frontend
@app.route('/')
def serve_frontend():
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../frontend', path)

if __name__ == '__main__':
    # Configuration pour le déploiement
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('app.log')
        ]
    )
    
    # Message de démarrage
    print("=" * 50)
    print("Service de transcription en démarrage...")
    print(f"Dossier de téléchargement: {os.path.abspath(app.config['UPLOAD_FOLDER'])}")
    
    # Ne pas importer directement d'un module à ce stade
    print(f"OpenAI API configurée: {'Oui' if openai.api_key else 'Non'}")
    print("=" * 50)
    
    # Démarrage du serveur
    app.run(host='0.0.0.0', port=5000, debug=True)