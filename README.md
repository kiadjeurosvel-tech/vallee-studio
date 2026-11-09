# Studio d'animation autonome — « La Vallée des Horizons »

Un épisode animé en 3D par jour, livré à **09:00 (Europe/Berlin)** dans les *Artifacts* GitHub,
**sans intervention humaine et sans aucun coût** : uniquement des logiciels et modèles libres,
exécutés sur les runners gratuits de GitHub Actions.

Format : vidéo verticale 1080×1920, H.264/AAC, 30 i/s, sous-titres incrustés, 45 à 75 s.

---

## 1. Ce que fait le studio, chaque jour

| Étape | Outil (licence) | Où |
|---|---|---|
| 1. Vérifier l'état, la mémoire figée, reprendre un épisode inachevé | Python, pytest | `preparer` |
| 2. Écrire le scénario | Qwen2.5 7B Instruct GGUF (Apache-2.0) via llama.cpp (MIT), sinon gabarits | `studio/narrative/` |
| 3. Vérifier le scénario (canon, personnages, longueur, dilemme) | validateur maison | `validate.py` |
| 4. Voix des personnages | Piper (GPL-3.0), voix `fr_FR` (rhasspy/piper-voices) ; secours eSpeak NG | `studio/audio/tts.py` |
| 5. Synchronisation labiale | Rhubarb Lip Sync (MIT) ; secours analyse acoustique | `lipsync.py` |
| 6. Mise en scène (plans, gestes, regards, émotions, marches) | réalisateur automatique | `studio/director.py` |
| 7. Animation 3D et rendu | Blender 4 (GPL), EEVEE, sur 1 à 12 machines en parallèle | `studio/animation/` |
| 8. Ambiances, bruitages, musique | synthèse numpy (aucun fichier tiers) | `soundscape.py` |
| 9. Montage, transitions, titres, sous-titres, carte de vote, mixage | FFmpeg (LGPL/GPL) + libass | `studio/edit/` |
| 10. Contrôle qualité (bloquant) | ffprobe, décodage complet, détection de noirs, saccades, volume | `studio/qa/` |
| 11. Livraison à 09:00 | GitHub Actions Artifacts (`episode-NNN`) | `livrer` |
| 12. Mémoire et mesures pour la suite | commit automatique | `memory/`, `episodes/`, `improvements/` |

### Ce que vous voyez à l'écran
- **Personnages 3D** construits à partir de leur fiche (`memory/characters.json`) : même visage, mêmes
  proportions, mêmes vêtements, mêmes couleurs, même voix à chaque épisode.
- **Marche** procédurale (cycle de pas calé sur la distance parcourue : pas de glissade), respiration,
  transferts de poids, **13 gestes** (`animations/gestures.json`), regards qui suivent l'interlocuteur,
  clignements, **8 expressions faciales** (sourcils, paupières, bouche), **lip-sync** par visèmes.
- **Caméra** : plans d'établissement en grue, plans larges, plans à deux, champ/contrechamp par-dessus
  l'épaule, gros plans avec **profondeur de champ**, révélations d'un lieu, travellings, léger « caméra à l'épaule ».
- **Décors vivants** à graine fixe (même lieu = même décor) : relief, rivière/lac animés, arbres et herbes
  dans le vent, feu de camp avec flammes, braises, fumée et lumière vacillante, brume volumétrique,
  pluie, lucioles la nuit, feuilles violettes qui tombent, cascade, lave, champignons phosphorescents.
- **Lumière** : 4 ambiances (aube, jour, crépuscule, nuit) avec ombres dynamiques douces, occlusion ambiante,
  halo (bloom), rendu AgX.
- **Transitions** : coupes franches dans une scène, fondu au noir entre deux scènes.

---

## 2. Installation (une seule fois, ≈ 5 minutes)

1. **Créer le dépôt** et y pousser ce projet (branche `main`).
2. **Rendre le dépôt public : fortement recommandé.** Voir « Limites » : en privé, les minutes gratuites
   ne suffisent pas pour un rendu 3D quotidien.
3. *Settings → Actions → General* : autoriser les workflows ; *Workflow permissions* : « Read and write ».
4. (Facultatif) Créer une issue intitulée **`VOTE`** : chaque commentaire `A` ou `B` compte pour
   l'épisode suivant. Sans vote, « le destin décide » (tirage reproductible), et la série continue.
5. Lancer une première production à la main : *Actions → Production quotidienne → Run workflow*
   (cocher `no_wait` pour ne pas attendre 09:00).

Aucun secret, aucune clé API, aucun compte payant.

### En local (Linux)
```bash
sudo apt install blender ffmpeg espeak-ng xvfb fonts-dejavu-core
pip install -r requirements.txt
pip install llama-cpp-python            # facultatif (scénarios par IA locale)
python -m pytest -q                      # tests (dont un rendu Blender de contrôle)
python -m studio.pipeline all --no-llm --preview   # épisode complet en basse définition
```

---

## 3. Organisation du dépôt

```
memory/                 MÉMOIRE PERMANENTE
  characters.json         10 personnages : bloc « reference » FIGÉ (apparence + voix) + personnalité, secrets
  world.json              canon, arcs, état du monde, historique des épisodes
  geography.json          carte 8×8, lieux, et « sets3d » : décor 3D figé de chaque lieu (graine fixe)
  visual_style.json       palette, lumières, caméra, sous-titres, format de sortie, bornes de réglage
  state.json              épisode courant, dernier dilemme, résumé
  reference.lock          empreinte des références : un test échoue si elles changent
story_queue/            scénarios écrits à la main (prioritaires sur l'IA) : epNNN.json
episodes/epNNN/         scénario produit + rapport qualité de chaque épisode
animations/gestures.json bibliothèque de gestes
studio/
  pipeline.py             orchestrateur (étapes reprenables)
  narrative/              moteur narratif : mémoire, LLM local, gabarits, validation
  director.py             réalisateur : découpage, plans, jeu d'acteurs, synchro
  audio/                  voix, lip-sync, ambiances/bruitages/musique
  animation/              moteur d'animation Blender (personnages, mouvements, décors, caméra, rendu)
  edit/                   montage, sous-titres, mixage
  qa/                     contrôle qualité
  improve.py              amélioration continue (mesures, backlog, réglage borné)
improvements/           metrics.jsonl, reports/, BACKLOG.md, tuning.json
config/studio.json      modèles LLM, nombre de machines de rendu, heure de livraison
tests/                  tests unitaires + rendu Blender de contrôle
.github/workflows/      production.yml, tests.yml, amelioration.yml
```

---

## 4. Robustesse

- **Reprise** : chaque étape lit et écrit `work/current/`. Les images déjà rendues sont gardées en cache
  (`actions/cache`) et ne sont jamais recalculées. Le second déclenchement (06:53 UTC) reprend un épisode
  inachevé. *Re-run failed jobs* ne relance que les lots de rendu en échec.
- **Repli** à chaque maillon : LLM → gabarits ; Piper → eSpeak NG ; Rhubarb → analyse acoustique ;
  moteur actuel → moteur étiqueté `stable` (le dernier qui a produit un épisode validé).
- **Jamais de fichier corrompu livré** : décodage intégral, format, durée et synchro vérifiés. En cas d'échec,
  la vidéo est renommée `REJETE.mp4` et rien n'est publié.
- **Transparence** : le moteur réellement utilisé (voix, lip-sync, source du scénario) est écrit dans le
  rapport qualité de chaque épisode (`episodes/epNNN/qa.md`).

## 5. Amélioration continue

Après chaque épisode validé : mesures (temps de rendu, saccades, images figées, volume, luminosité, durée
des plans…) ajoutées à `improvements/metrics.jsonl`, rapport daté, `BACKLOG.md` (défauts récurrents triés).
Le workflow **Amélioration continue** ajuste *uniquement* `improvements/tuning.json` (échantillons, résolution
interne) **dans les bornes** de `visual_style.json`, selon la marge de temps de rendu, puis **relance tous les
tests** (dont un rendu réel) avant d'enregistrer. Le code du moteur n'est jamais modifié automatiquement :
les évolutions de code passent par une PR, testée par `tests.yml`, et par l'étiquette `stable` en cas de régression.

---

## 6. Limites (honnêtes) et alternatives gratuites

| Souhait | Réalité gratuite | Ce que fait le studio |
|---|---|---|
| GPU | Les runners GitHub gratuits n'ont **pas de GPU** (4 vCPU, 16 Go) | EEVEE en rendu logiciel, réparti sur jusqu'à 12 machines, résolution interne 720×1280 puis agrandissement Lanczos + accentuation |
| Minutes illimitées | **Illimitées seulement pour un dépôt public**. Privé (offre Free) : 2 000 min/mois, partagées avec vos autres dépôts privés | Un épisode ≈ 150 à 250 min-machine → **dépôt public obligatoire** pour un épisode/jour. En privé : mettre `max_jobs` à 1–2 et `res_x` à 540, `samples` à 4, ou produire un épisode tous les 3 à 4 jours |
| Livraison à 09:00 pile | Les crons GitHub sont en UTC et peuvent être retardés (jusqu'à ~1 h en période chargée) | Démarrage à 06:23/07:23 (Berlin), reprise à 07:53/08:53, attente active jusqu'à 09:00 : vidéo livrée à 09:00 sauf retard exceptionnel de GitHub |
| Qualité « film d'animation » | Les modèles vidéo IA (génération d'images animées) exigent un GPU | Animation 3D procédurale stylisée, cohérente et stable ; la qualité monte avec les réglages et les évolutions du moteur |
| Scénarios de haut niveau | Un 7B local sur CPU écrit correctement mais moins bien qu'un grand modèle | Prompt riche (canon, arcs, secrets), validation stricte, 3 essais, puis gabarits ; `story_queue/` pour les épisodes clés écrits à la main |
| Lip-sync parfait en français | Rhubarb est conçu pour l'anglais (mode phonétique utilisé) | Visèmes calés au 1/30 s sur l'audio réel ; précision correcte sur le rythme, approximative sur certaines consonnes |
| Stockage des vidéos | Artifacts : 500 Mo en privé, rétention limitée | Rétention 30 jours, ~40 Mo par épisode ; téléchargez/publiez chaque jour |

Durée estimée d'une production (dépôt public) : préparation 10–15 min (dont LLM 3–6 min), rendu 20–30 min
en parallèle, montage 3–5 min.

## 7. Maintenance

- **Écrire un épisode à la main** : déposer `story_queue/epNNN.json` (format de `ep001.json`).
- **Changer volontairement l'apparence d'un personnage ou d'un décor** : modifier `memory/…`, puis
  `python -m studio.lock_reference` et committer (sinon le test de cohérence bloque la production).
- **Ajouter un geste** : `animations/gestures.json`, puis vérifier avec `pytest -m blender`.
- **Plus de qualité** : augmenter `max_jobs` (config) puis laisser l'auto-réglage monter les échantillons.
- **Revenir en arrière** : `git checkout stable -- studio/` (dernier moteur validé en production).
- **Surveiller** : `improvements/BACKLOG.md`, rapports `episodes/epNNN/qa.md`, onglet Actions.

Licences des composants : voir [THIRD_PARTY.md](THIRD_PARTY.md). Historique : [CHANGELOG.md](CHANGELOG.md).
