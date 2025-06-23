class TranscriptionApp {
    constructor() {
        this.apiUrl = 'http://localhost:5000/api';
        this.isRecording = false;
        this.audioChunks = [];
        this.failedSegments = [];
        this.mediaRecorder = null;
        this.audioContext = null;
        this.analyser = null;
        this.segments = [];
        this.audioInterval = null;
        this.segmentCounter = 0;          // Compteur de segments
        this.pendingSegments = new Map(); // Pour suivre les segments en cours
        this.processedSegments = new Map(); // Map pour stocker les segments traités
        this.transcriptionSegments = new Map();

        this.initElements();
        this.initEventListeners();
        this.updateStatus('Prêt');
        this.testApiConnection();
    }

    initElements() {
        this.startBtn = document.getElementById('start-btn');
        this.stopBtn = document.getElementById('stop-btn');
        this.consolidateBtn = document.getElementById('consolidate-btn');
        this.clearBtn = document.getElementById('clear-btn');
        this.saveBtn = document.getElementById('save-btn');
        this.reportBtn = document.getElementById('report-btn');
        this.retryBtn = document.getElementById('retry-btn');

        this.bilingualTranscription = document.getElementById('bilingual-transcription');
        this.finalTranscription = document.getElementById('final-transcription');
        this.medicalReport = document.getElementById('medical-report');

        this.statusIndicator = document.getElementById('status-indicator');
        this.audioLevel = document.getElementById('audio-level');
        this.audioLevelValue = document.getElementById('audio-level-value');

        this.reportModal = new bootstrap.Modal(document.getElementById('report-modal'));
    }

    initEventListeners() {
        if (this.startBtn) this.startBtn.addEventListener('click', () => this.startRecording());
        if (this.stopBtn) this.stopBtn.addEventListener('click', () => this.stopRecording());
        if (this.consolidateBtn) this.consolidateBtn.addEventListener('click', () => this.consolidateAllSegments());
        if (this.clearBtn) this.clearBtn.addEventListener('click', () => this.clearAll());
        if (this.saveBtn) this.saveBtn.addEventListener('click', () => this.saveTranscription());
        if (this.reportBtn) this.reportBtn.addEventListener('click', () => this.generateReport());
        if (this.retryBtn) this.retryBtn.addEventListener('click', () => this.retryFailedSegments());
    }

    async testApiConnection() {
        try {
            const response = await fetch(`${this.apiUrl}/debug/test-transcription`);
            if (response.ok) {
                const data = await response.json();
                if (data.status === "success" && data.data) {
                    // Initialiser les zones de texte avec le test
                    this.initializeTranscriptionAreas(data.data);
                    this.updateStatus('API connectée - Test réussi');
                }
            } else {
                this.updateStatus('Erreur de connexion API');
            }
        } catch {
            this.updateStatus('API non disponible');
        }
    }

    initializeTranscriptionAreas(data) {
        if (this.bilingualTranscription && data) {
            const initialContent = [
                'Test de connexion:',
                data.darija ? `Darija: ${data.darija}` : '',
                data.french ? `Français: ${data.french}` : '',
                '---'
            ].filter(line => line).join('\n');
            
            this.bilingualTranscription.value = initialContent;
        }
        
        if (this.finalTranscription && data && data.fused) {
            this.finalTranscription.value = `Test API: ${data.fused}`;
        }
    }

    displaySegmentPlaceholder(segmentId) {
        if (!this.bilingualTranscription) return;
        
        const position = this.pendingSegments.get(segmentId).position;
        const currentText = this.bilingualTranscription.value;
        const lines = currentText.split('\n');
        
        // S'assurer qu'il n'y a pas déjà un placeholder pour ce segment
        const existingPlaceholder = lines.findIndex(line => 
            line.includes(`(Transcription du segment ${position} en cours...)`));
        if (existingPlaceholder !== -1) return;
        
        // Ajouter le placeholder à la fin
        lines.push('', `(Transcription du segment ${position} en cours...)`);
        this.bilingualTranscription.value = lines.join('\n');
    }

    async startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, sampleRate: 16000, channelCount: 1 }
            });

            const options = MediaRecorder.isTypeSupported('audio/webm') ? { mimeType: 'audio/webm' } : {};
            this.mediaRecorder = new MediaRecorder(stream, options);
            this.audioChunks = [];
            this.segments = [];
            this.failedSegments = [];

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) this.audioChunks.push(event.data);
            };

            this.mediaRecorder.onstop = () => this.processAudioChunk();

            this.mediaRecorder.start();
            this.isRecording = true;
            this.startBtn.disabled = true;
            this.stopBtn.disabled = false;
            this.updateStatus('Enregistrement en cours...');
            this.startAudioAnalysis(stream);

            this.audioInterval = setInterval(() => {
                if (this.isRecording && this.mediaRecorder.state === 'recording') {
                    this.mediaRecorder.stop();
                    this.mediaRecorder.start();
                }
            }, 5000);

        } catch (error) {
            this.updateStatus(`Erreur: ${error.message}`);
        }
    }

    stopRecording() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;

            clearInterval(this.audioInterval);
            this.audioInterval = null;

            if (this.audioContext) {
                this.audioContext.close();
                this.audioContext = null;
            }

            this.startBtn.disabled = false;
            this.stopBtn.disabled = true;
            this.updateStatus('Traitement final...');

            setTimeout(() => {
                this.consolidateAllSegments();
                if (this.failedSegments.length > 0) {
                    this.updateStatus(`Attention : ${this.failedSegments.length} segment(s) non transcrit(s). Cliquez sur "Réessayer Segments Échoués"`);
                }
            }, 1000);
        }
    }

    isValidContent(text) {
        if (!text) return false;
        
        // Liste de phrases à ignorer
        const invalidPhrases = [
            "شكرا على المشاهدة",
            "localisation",
            "merci d'avoir regardé",
            "abonnez-vous",
            "like et partage",
            "اشترك في القناة"
        ];
        
        // Vérifier si le texte contient une des phrases à ignorer
        return !invalidPhrases.some(phrase => 
            text.toLowerCase().includes(phrase.toLowerCase()));
    }

    isValidSegment(data) {
        // Vérifier si au moins une transcription valide existe
        const hasDarija = data.darija && this.isValidContent(data.darija);
        const hasFrench = data.french && this.isValidContent(data.french);
        const hasFused = data.fused && this.isValidContent(data.fused);
        
        // Le segment est valide s'il a au moins une transcription valide
        return hasDarija || hasFrench || hasFused;
    }

    async processAudioChunk() {
        if (this.audioChunks.length === 0) return;

        const currentChunks = [...this.audioChunks];
        this.audioChunks = [];
        const segmentId = Date.now().toString();
        
        // Ajouter un placeholder pour ce segment
        const position = this.processedSegments.size + 1;
        this.pendingSegments.set(segmentId, {
            status: 'processing',
            position: position
        });
        
        // Afficher le placeholder
        this.displaySegmentPlaceholder(segmentId);

        try {
            const audioBlob = new Blob(currentChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('file', audioBlob, `segment_${segmentId}.wav`);

            const response = await fetch(`${this.apiUrl}/transcribe/process`, { 
                method: 'POST', 
                body: formData,
                signal: AbortSignal.timeout(30000)
            });

            if (!response.ok) throw new Error(`Erreur ${response.status}`);

            const result = await response.json();
            console.log("Réponse reçue:", result);

            if (result.status === 'success' && result.data) {
                const hasContent = result.data.darija || result.data.french || result.data.fused;
                if (hasContent) {
                    this.updateSegment(segmentId, result.data);
                    this.processedSegments.set(position, result.data);
                    this.removeExcessPlaceholders();
                }
            }

        } catch (error) {
            console.error("Erreur de traitement:", error);
            this.handleFailedSegment(segmentId, currentChunks);
        }
    }

    displaySegmentPlaceholder(segmentId) {
        if (!this.bilingualTranscription) return;
        
        const position = this.pendingSegments.get(segmentId).position;
        const currentText = this.bilingualTranscription.value;
        const lines = currentText.split('\n');
        
        // Ne garder qu'un nombre limité de placeholders (max 3)
        const placeholderLines = lines.filter(line => line.includes('en cours...'));
        if (placeholderLines.length >= 3) return;
        
        // Ajouter le nouveau placeholder
        lines.push('', `(Transcription du segment ${position} en cours...)`);
        this.bilingualTranscription.value = lines.join('\n');
    }

    removeExcessPlaceholders() {
        if (!this.bilingualTranscription) return;
        
        const lines = this.bilingualTranscription.value.split('\n');
        const filteredLines = lines.filter(line => !line.includes('en cours...'));
        this.bilingualTranscription.value = filteredLines.join('\n');
    }

    updateSegment(segmentId, data) {
        if (!this.bilingualTranscription || !this.pendingSegments.has(segmentId)) return;
        
        const position = this.pendingSegments.get(segmentId).position;
        const currentText = this.bilingualTranscription.value;
        const lines = currentText.split('\n');

        // Supprimer les placeholders existants
        const filteredLines = lines.filter(line => !line.includes('en cours...'));

        // Ajouter les nouvelles lignes à la fin
        const segmentLines = [
            '',
            `Segment ${position}:`,
            data.darija ? `Darija: ${data.darija}` : '',
            data.french ? `Français: ${data.french}` : '',
            data.fused ? `Reformulation: ${data.fused}` : '',
            '---'
        ].filter(line => line !== '');

        filteredLines.push(...segmentLines);

        // Mettre à jour l'affichage
        this.bilingualTranscription.value = filteredLines.join('\n');
        this.transcriptionSegments.set(position, data);
        this.pendingSegments.delete(segmentId);
    }

    async consolidateAllSegments() {
        // Récupérer tous les segments dans l'ordre
        const segments = Array.from(this.transcriptionSegments.entries())
            .sort(([posA], [posB]) => posA - posB) // Trier par position
            .map(([_, segment]) => segment)
            .filter(segment => segment && (segment.darija || segment.french || segment.fused));

        if (segments.length === 0) {
            this.updateStatus('Aucun segment à consolider');
            return;
        }

        try {
            this.updateStatus('Consolidation des segments...');
            const response = await fetch(`${this.apiUrl}/transcription/consolidate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ segments: segments })
            });

            if (!response.ok) {
                throw new Error(`Erreur HTTP: ${response.status}`);
            }

            const result = await response.json();
            if (result.status === "success" && result.data) {
                if (this.finalTranscription) {
                    this.finalTranscription.value = result.data;
                }
                this.updateStatus('Consolidation terminée');
            } else {
                throw new Error(result.message || "Erreur de consolidation");
            }
        } catch (error) {
            console.error('Erreur lors de la consolidation:', error);
            // Fallback : concaténer les segments dans l'ordre
            if (this.finalTranscription) {
                const consolidatedText = segments
                    .map(segment => segment.fused || segment.french || segment.darija)
                    .filter(text => text)
                    .join("\n");
                this.finalTranscription.value = consolidatedText;
            }
            this.updateStatus('Consolidation simple effectuée');
        }
    }

    async retryFailedSegments() {
        if (this.failedSegments.length === 0) {
            this.updateStatus("Aucun segment à réessayer");
            return;
        }

        this.updateStatus(`Reprise de ${this.failedSegments.length} segment(s) échoué(s)...`);

        for (let i = 0; i < this.failedSegments.length; i++) {
            const audioBlob = new Blob(this.failedSegments[i], { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('file', audioBlob, `retry_segment_${i}.webm`);

            try {
                const response = await fetch(`${this.apiUrl}/transcribe/process`, { method: 'POST', body: formData });
                const result = await response.json();

                if (result.status === "success" && result.data?.fused?.trim()) {
                    this.segments.push(result.data.fused);
                    this.displayTranscriptionResults(result.data);
                }
            } catch (error) {
                console.error(`Erreur segment #${i + 1} :`, error);
            }
        }

        this.failedSegments = [];
        this.updateStatus("Récupération terminée");
    }

    startAudioAnalysis(stream) {
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.analyser = this.audioContext.createAnalyser();
            const source = this.audioContext.createMediaStreamSource(stream);
            source.connect(this.analyser);
            this.analyser.fftSize = 256;

            const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
            const updateLevel = () => {
                if (this.analyser && this.isRecording) {
                    this.analyser.getByteFrequencyData(dataArray);
                    const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
                    const level = Math.min(100, (average / 128) * 100);
                    if (this.audioLevel) this.audioLevel.style.width = `${level}%`;
                    if (this.audioLevelValue) this.audioLevelValue.textContent = Math.round(level);
                    requestAnimationFrame(updateLevel);
                }
            };

            updateLevel();
        } catch (error) {
            console.error('Erreur analyse audio:', error);
        }
    }

    async generateReport() {
        const transcription = this.finalTranscription?.value?.trim();
        if (!transcription) return this.updateStatus('Aucune transcription à analyser');

        try {
            const response = await fetch(`${this.apiUrl}/report/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ transcription })
            });

            const result = await response.json();
            if (result.status === "success" && result.data) {
                if (this.medicalReport) {
                    this.medicalReport.value = result.data;
                    this.reportModal.show();
                }
                this.updateStatus('Rapport généré');
            } else {
                throw new Error(result.message || 'Erreur génération rapport');
            }
        } catch (error) {
            this.updateStatus(`Erreur: ${error.message}`);
        }
    }

    async saveTranscription() {
        const text = this.finalTranscription?.value?.trim();
        if (!text) return this.updateStatus('Aucune transcription à enregistrer');

        try {
            const response = await fetch(`${this.apiUrl}/transcription/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });

            const result = await response.json();
            if (result.status === 'success') {
                const blob = new Blob([text], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `transcription_${new Date().toISOString().slice(0,10)}.txt`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                this.updateStatus('Transcription enregistrée');
            }
        } catch (error) {
            this.updateStatus(`Erreur: ${error.message}`);
        }
    }

    clearAll() {
        this.pendingSegments.clear();
        this.processedSegments.clear();
        this.transcriptionSegments.clear();
        this.failedSegments = [];
        
        if (this.bilingualTranscription) {
            this.bilingualTranscription.value = '';
        }
        if (this.finalTranscription) {
            this.finalTranscription.value = '';
        }
        
        this.updateStatus('Transcription effacée');
    }

    updateStatus(message) {
        if (this.statusIndicator) {
            // N'afficher que les messages importants
            if (!message.includes('en cours') && !message.includes('processing')) {
                this.statusIndicator.textContent = message;
            }
        }
        console.log('Status:', message);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.transcriptionApp = new TranscriptionApp();
});
