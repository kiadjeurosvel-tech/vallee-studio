# Journal des versions

Les réglages automatiques (amélioration continue) sont ajoutés en bas de ce fichier par le workflow.

## 1.0.0 — 2026-11-09
- Moteur d'animation Blender : personnages procéduraux à partir de fiches figées (10 fondateurs),
  marche calée sur la distance, 13 gestes, regards, clignements, 8 expressions, visèmes.
- Décors à graine fixe pour les 8 lieux de la carte : végétation au vent, eau animée, feu, fumée, braises,
  pluie, lucioles, feuilles, cascade, lave, grotte ; 4 ambiances lumineuses ; brume volumétrique.
- Caméra automatique : établissement, large, plan à deux, gros plan (profondeur de champ), par-dessus l'épaule,
  révélation de lieu, travelling ; évitement des obstacles et couloir caméra dans chaque décor.
- Moteur narratif : LLM local (llama.cpp, Qwen2.5 Apache-2.0) + validation stricte + gabarits de secours.
- Audio : Piper / eSpeak NG, lip-sync Rhubarb / acoustique, ambiances, bruitages et musique synthétisés.
- Montage FFmpeg : 1080×1920 H.264/AAC 30 i/s, titres, sous-titres ASS, carte de vote, fondus, loudnorm -14 LUFS.
- Contrôle qualité bloquant, mesures, backlog, réglage automatique borné, étiquette `stable` de repli.
- Workflows : production quotidienne (livraison 09:00 Berlin), tests, amélioration continue.

## 1.0.1 — 2026-11-09 (après le premier épisode réel)
- Livraison : chemin de l'artefact final corrigé (la vidéo était produite et validée mais pas publiée).
- Blender : cache des paquets apt (une machine avait mis 19 min à l'installer), avec repli apt.
- Caches séparés voix Piper / modèle de langage (le modèle de 4,7 Go n'est téléchargé qu'une fois).
- Plans « révélation » : panoramique plus lent et plan plus long (22 saccades signalées par la QA de l'épisode 1).
- Les mesures de rendu ne sont plus effacées lors d'une reprise.
