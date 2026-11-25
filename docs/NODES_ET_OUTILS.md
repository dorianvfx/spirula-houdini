# Nodes et outils : à quoi sert quoi

Mis à jour en novembre 2026 après l'audit. Il y a **31 types de nodes** dans `otls/`. Seuls 2 sont visibles dans le menu Tab ; les 29 autres sont créés automatiquement par les outils de l'étagère (ils ne fonctionnent pas seuls).

## Outils de l'étagère « Spirula » (menu Tab : taper « spirula »)

| Outil | Ce qu'il crée / fait | À utiliser quand |
|---|---|---|
| **Spirula Pipeline** | Un objet `SPIRULA_CHAINE` avec les étapes 01 → 10 (voir plus bas) et ouvre Spirula Studio. | Tu pars de photos/vidéo et tu veux le parcours guidé complet. |
| **Spirula Scene Karma** | Une chaîne `arch_*` 01 → 07 (scène Solaris/Karma → caméras → rendus → splat → export). | Tu as une scène 3D entièrement modélisée et éclairée (extérieur, bâtiment, pièce) à transformer en splat. |
| **Spirula Studio** | Le panneau Studio natif (le vrai viewport de Spirula) dans Houdini. | Tu veux seulement le Studio, sans la chaîne. |
| **Spirula Raffinement local** | Quatre nodes 06A → 06D après un splat. | Tu veux améliorer *une zone* (gros plans Karma ou photos) avec Avant/Après. |
| **Spirula Raffiner par apprentissage** | Un node `spirula::polish` après un splat. | Tu veux continuer l'entraînement de *tout* le splat avec ses photos. |
| **Spirula Nettoyer les floaters** | Un node `spirula::clean_floaters` après un splat. | Tu veux retirer les gaussiennes parasites. |
| Assemble / Cut / Insert / Object to Splat / Render to Splat (« Avancé ») | Les nodes `spirula::assemble_splats`, `cut_splats`, `insert_asset`, `object_splat`, `render_splat`. | Usage manuel hors parcours guidé. |

Si un outil échoue : boîte de dialogue + `%TEMP%\spirula_errors.log`.

## La chaîne « Spirula Pipeline » (photos)

01 Photos dans Spirula → 02 Scan orienté → (02A–02E facultatif : sélection, retrait, estimation du fond, conversion, scan réparé) → 03 Objet 3D → 04 Placement → 05 Éclairage par le scan → 06 Caméras de capture → 07 Rendus Karma → 08 Apprentissage du splat → 09 Assemblage scan + objet → 10 Export et répétition.

## La chaîne « Scene Karma »

01 Scène Solaris → 02 Caméras → 03 Aperçu Karma → 04 Rendus Karma → 05 Apparence et génération du splat → 06 Splat dans le viewport → 07 Export PLY. Voir [ARCHITECTURE_KARMA.md](ARCHITECTURE_KARMA.md).

## Les deux nodes visibles dans le menu Tab

### `spirula::polish` — Raffiner par apprentissage
- **Entrées** : un splat. **Paramètres** : dossier photos + caméras (COLMAP `sparse/0` ou `transforms.json`), PLY de départ (vide = exporter l'entrée), qualité (rapide / standard / maximum), étapes, mise de côté d'une photo sur 8 pour mesurer.
- **Boutons** : Lancer (calcul en arrière-plan avec le moteur Spirula), Actualiser (progression), Arrêter.
- **Résultat** : le paramètre « Afficher » bascule entre le splat d'entrée et le splat raffiné. Le fichier d'origine n'est jamais modifié.
- **Ce que ça fait** : reprend le PLY comme point de départ (`--init-ply`), garde les réglages de placement du premier entraînement s'ils sont trouvés à côté du PLY, et laisse le moteur ajouter des gaussiennes là où les photos montrent plus de détail.
- **Limite mesurée** : sur le scan testé, pas de gain démontré (voir [RESULTATS_MESURES.md](RESULTATS_MESURES.md)).
- Module : `python3.13libs/spirula_polish.py` (utilisable aussi en ligne de commande).

### `spirula::clean_floaters` — Nettoyer les floaters
- Tag chaque gaussienne `spirula_floater=1` si elle est : quasi invisible (opacité < 0,005 par défaut), géante par rapport à la scène (voile), ou isolée **et** faible (opacité < 0,25, moins de 3 voisins dans un voxel proportionnel à sa propre taille).
- Les structures fines **opaques** ne sont jamais retirées pour cause d'isolement.
- **Mode** : Retirer / Voir seulement ce qui serait retiré / Désactivé. Un message indique le décompte par catégorie.
- Module : `python3.13libs/spirula_clean.py` (CLI : `hython spirula_clean.py in.ply out.ply`).

## Les 29 nodes internes (masqués du menu Tab)

Créés par les outils ci-dessus ; `python3.13libs/pythonrc.py` les masque au démarrage de Houdini. Ils restent entièrement fonctionnels dans les réseaux générés.

| Famille | Nodes |
|---|---|
| Scene Karma | `arch_source`, `arch_cameras`, `arch_preview`, `arch_renders`, `arch_train`, `arch_result`, `arch_export` |
| Pipeline photos | `chain_scan`, `chain_mesh`, `chain_light`, `chain_cameras`, `chain_render`, `chain_train`, `chain_assemble`, `chain_export` |
| Remplacement d'objet | `replace_selection`, `replace_remove`, `replace_repair`, `repair_planes` |
| Raffinement local | `refine_zone`, `refine_renders`, `refine_apply`, `refine_check` |
| Briques | `studio`, `render_splat`, `object_splat`, `assemble_splats`, `cut_splats`, `insert_asset` |

## Modules Python (python3.13libs/)

| Module | Rôle |
|---|---|
| `spirula_ply.py` | Export PLY 3DGS standard, rotation des harmoniques sphériques. |
| `spirula_transform.py` | Applique une transformation (rotation, échelle) aux gaussiennes : position, covariance, couleur. |
| `spirula_native.py`, `spirula_studio_panel.py` | Héberge le vrai viewport de Spirula dans un panneau Houdini (Qt + Win32). |
| `spirula_houdini.py` | Pont Houdini ↔ Studio : envoi du modèle, import de mesh, ouverture du panneau. |
| `spirula_chain.py`, `spirula_arch.py` | Construisent les chaînes guidées Pipeline et Scene Karma. |
| `spirula_render.py`, `spirula_workflow.py`, `spirula_monitor.py` | Rendus Karma, jobs d'apprentissage, suivi de progression. |
| `spirula_object.py`, `spirula_insert.py`, `spirula_scene.py`, `spirula_surface_bake.py` | Objet 3D → splat, insertion, assemblage/découpe. |
| `spirula_replace.py`, `spirula_repair.py` | Sélection, retrait et estimation du fond d'un objet de scan. |
| `spirula_refine.py`, `spirula_refine_colmap.py` | Raffinement local d'une zone (Karma ou photos, COLMAP/Nerfstudio). |
| `spirula_polish.py` | Raffinement de tout un splat par apprentissage. |
| `spirula_clean.py` | Nettoyage de floaters. |
| `spirula_quality.py`, `spirula_exchange.py`, `spirula_train_profiles.py`, `spirula_runtime.py` | Contrôles du pipeline, export SOG/SPZ, profils d'entraînement, choix de la version du moteur. |
| `spirula_tools.py` | Points d'entrée de l'étagère, avec erreurs visibles. |
| `spirula_web_panel.py` | Panneau de suivi de l'entraînement en ligne de commande. |
| `spirula_house_demo.py` | Petite maison procédurale pour la démo Scene Karma. |
| `spirula_selftest.py` | Tests (voir README). |
