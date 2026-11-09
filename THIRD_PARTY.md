# Composants tiers et licences

Tous les composants sont gratuits. Les vidéos produites ne sont pas des « œuvres dérivées » des logiciels
utilisés pour les créer (Blender, FFmpeg, Piper, eSpeak NG : la licence GPL s'applique au logiciel, pas à ce
qu'il produit). Vérifiez les points marqués ⚠ avant un usage commercial.

| Composant | Rôle | Licence | Remarques |
|---|---|---|---|
| Blender 4.x (paquet Ubuntu) | modélisation, animation, rendu EEVEE | GPL-2.0+ | les rendus appartiennent à l'auteur |
| FFmpeg + libx264 + libass | montage, encodage H.264/AAC, sous-titres | LGPL/GPL | encodeur AAC natif de FFmpeg |
| Piper (`piper-tts`, OHF-Voice/piper1-gpl) | synthèse vocale | GPL-3.0 | appelé comme outil |
| Voix Piper `fr_FR-siwis`, `fr_FR-upmc`, `fr_FR-tom`, `fr_FR-gilles` | voix des personnages | dépôt `rhasspy/piper-voices` (MIT) ; jeu de données d'origine propre à chaque voix | ⚠ le `MODEL_CARD` de chaque voix est téléchargé à côté du modèle (`.cache/piper/*.MODEL_CARD`) : lire les conditions du jeu de données avant un usage commercial ; remplacer la voix dans `characters.json` si besoin |
| eSpeak NG | voix de secours | GPL-3.0 | |
| Rhubarb Lip Sync 1.13 | visèmes | MIT | mode phonétique (indépendant de la langue) |
| llama.cpp / llama-cpp-python | inférence LLM sur CPU | MIT | |
| Qwen2.5-7B-Instruct / 1.5B-Instruct (GGUF de bartowski) | scénarios | Apache-2.0 | ne pas utiliser Qwen2.5-3B (licence de recherche, non commerciale) |
| numpy, Pillow, pytest | calcul, images, tests | BSD / MIT-CMU / MIT | |
| Police DejaVu Sans | sous-titres | licence libre Bitstream Vera / domaine public | |
| Musique, ambiances, bruitages | synthèse procédurale du studio | code du dépôt | aucun échantillon externe |
| Personnages, décors, univers | créations originales du dépôt (canon issu de « La Vallée des Horizons ») | — | |

Technologies évaluées et écartées (pour l'instant) :
- **Manim** (MIT) : excellent pour les schémas animés, inutile pour une série de personnages 3D.
- **Génération vidéo/image par diffusion** (Stable Video Diffusion, AnimateDiff, etc.) : nécessite un GPU ;
  sur CPU, plusieurs minutes par image ; licences parfois non commerciales. Incompatible avec 0 € et 09:00.
- **Wav2Lip / SadTalker** : visages réalistes en 2D, GPU recommandé, licences non commerciales (Wav2Lip).
- **Cycles** (Blender) : meilleur rendu, mais 10 à 50 fois plus lent qu'EEVEE sur CPU.
