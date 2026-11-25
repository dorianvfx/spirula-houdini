# Spirula × Houdini

Intégration de [Spirula Studio](https://github.com/harry7557558/spirula-studio) dans **Houdini 22** : faire un splat gaussien à partir de photos ou de vidéo, le voir et le modifier dans Houdini, y insérer ou y remplacer des objets 3D (rendus avec Karma), puis exporter le résultat.

> **État du projet : outil de travail, pas un produit fini.** Il a été développé et testé sur une seule machine (Windows 11, Houdini 22.0.368, carte AMD Radeon RX 7800 XT en Vulkan). La qualité finale n'a pas été validée sur plusieurs scans réels. Voir [Limites connues](#limites-connues) et [docs/RESULTATS_MESURES.md](docs/RESULTATS_MESURES.md).

## Ce que fait l'outil

| Besoin | Outil (étagère « Spirula » / menu Tab) | Détail |
|---|---|---|
| Photos ou vidéo → splat, dans Houdini | **Spirula Pipeline** (chaîne 01 → 10) | Ouvre Spirula Studio dans un panneau Houdini, reçoit le scan, puis guide les étapes. |
| Scène 3D éclairée → splat | **Spirula Scene Karma** (chaîne 01 → 07) | Rend des centaines de vues avec Karma, entraîne un splat à partir de ces rendus. Pour les visites architecturales. |
| Ouvrir le vrai Spirula dans Houdini | **Spirula Studio** | Le moteur de rendu natif de Spirula est hébergé dans un panneau Houdini. |
| Améliorer une zone d'un splat | **Spirula Raffinement local** (06A → 06D) | Réapprend une zone avec des rendus rapprochés ou des photos, avec comparaison Avant/Après. |
| Raffiner tout un splat avec ses photos | **Spirula Raffiner par apprentissage** | Continue l'entraînement en pleine résolution avec densification. Voir [docs/NODES_ET_OUTILS.md](docs/NODES_ET_OUTILS.md). |
| Retirer les gaussiennes parasites | **Spirula Nettoyer les floaters** | Retire les gaussiennes presque invisibles, géantes ou isolées. Mode « voir ce qui serait retiré ». |
| Remplacer un objet du scan | Étapes 02A → 02E de la chaîne Pipeline | Sélection, retrait, estimation du fond, conversion en splats. |
| Exporter | Étapes d'export des chaînes | PLY standard 3DGS, SOG et SPZ (via PlayCanvas SplatTransform), BGEO. |

Outils « Avancé » (Assemble, Cut, Insert, Object to Splat, Render to Splat) : disponibles sur l'étagère pour un usage manuel.

## Prérequis

- Windows 11 (le panneau Studio utilise des appels Win32).
- Houdini **22.0.368** (testé uniquement avec cette version).
- Une carte graphique compatible Vulkan pour l'entraînement Spirula.
- Le moteur **Spirula** (non inclus dans ce dépôt, voir [runtime/README.md](runtime/README.md)).

## Installation

1. Cloner ce dépôt.
2. Récupérer le moteur Spirula et le placer dans `runtime/` : voir [runtime/README.md](runtime/README.md).
3. Lancer `Install.ps1` (clic droit → Exécuter avec PowerShell). Il écrit le package Houdini `spirula-studio.json` dans `Documents\houdini22.0\packages\` qui pointe sur ce dossier, et crée un raccourci « Spirula Pipeline » sur le Bureau.
4. Démarrer Houdini. Dans un réseau Objet ou SOP, ouvrir le menu Tab et taper « spirula », ou utiliser l'étagère **Spirula**.

Si un outil échoue, une boîte de dialogue s'ouvre et l'erreur est aussi écrite dans `%TEMP%\spirula_errors.log`.

## Structure du dépôt

```
README.md                    ce fichier
LICENSE.txt, NOTICE.txt      voir « Licences »
Install.ps1                  installe le package Houdini (chemin + raccourci)
Ouvrir_*.cmd                 lanceurs Houdini (pipeline, architecture, studio)
python3.13libs/              tout le code Python (modules spirula_*.py)
  pythonrc.py                masque du menu Tab les nodes internes (démarrage Houdini)
  spirula_selftest.py        suite de tests (voir « Tests »)
otls/                        les nodes Houdini (fichiers .hda)
toolbar/spirula.shelf        l'étagère et les outils du menu Tab
python_panels/               les panneaux (Studio natif, suivi d'entraînement)
scripts/                     scripts qui reconstruisent les .hda et les exemples
docs/                        documentation (voir ci-dessous)
runtime/                     moteur Spirula : non versionné, instructions dedans
third_party/                 provenance du moteur (version, empreinte SHA-256)
examples/                    scènes d'exemple : non versionnées, voir examples/README.md
```

## Documentation

| Document | Contenu |
|---|---|
| [docs/NODES_ET_OUTILS.md](docs/NODES_ET_OUTILS.md) | Chaque outil et chaque node : à quoi il sert, quand l'utiliser, ce qui est masqué du menu Tab. |
| [docs/ARCHITECTURE_KARMA.md](docs/ARCHITECTURE_KARMA.md) | La chaîne scène 3D → rendus Karma → splat. |
| [docs/REMPLACER_UN_OBJET.md](docs/REMPLACER_UN_OBJET.md) | Retirer et remplacer un objet d'un scan. |
| [docs/RAFFINEMENT_LOCAL.md](docs/RAFFINEMENT_LOCAL.md) | Raffinement d'une zone (06A → 06D). |
| [docs/MANUEL_AVANCE.md](docs/MANUEL_AVANCE.md) | Manuel détaillé. |
| [docs/RESULTATS_MESURES.md](docs/RESULTATS_MESURES.md) | Tous les chiffres mesurés, avec leurs limites. |
| [docs/AUDIT_2026-11.md](docs/AUDIT_2026-11.md) | Audit du code, défauts corrigés, ajouts. |
| [docs/RECHERCHE_RAFFINEMENT.md](docs/RECHERCHE_RAFFINEMENT.md), [docs/RECHERCHE_SIGGRAPH_ET_OUTILS.md](docs/RECHERCHE_SIGGRAPH_ET_OUTILS.md) | Ce qui existe (articles, outils, dépôts) et ce qui est compatible AMD. |
| [docs/HISTORIQUE_VERSIONS_CODEX.md](docs/HISTORIQUE_VERSIONS_CODEX.md) | Journal des versions 6 à 7.3, tel que rédigé pendant le développement. |

## Tests

```
"C:\Program Files\Side Effects Software\Houdini 22.0.368\bin\hython.exe" python3.13libs\spirula_selftest.py
```

11 tests, tous passés au dernier essai. Ils vérifient : la base des harmoniques sphériques (couleur selon l'angle de vue) contre la référence 3DGS, leur rotation, la transformation d'un splat (rotation, échelle uniforme, échelle non uniforme) suivie d'un export PLY, la résolution de la version du moteur, le nettoyage des floaters sur données synthétiques, l'import de tous les modules, le menu Tab et le fait que les erreurs d'outils ne sont pas avalées. Ils ne vérifient **pas** l'interface de Houdini ni la qualité visuelle d'un splat.

## Limites connues

- Qualité non validée sur plusieurs scans réels : un seul scan d'intérieur (390 images tirées d'une vidéo) a été mesuré en détail.
- Le raffinement par apprentissage n'a pas montré de gain démontré sur ce scan (voir les mesures).
- Mip et 3DGUT sont sélectionnables mais restent en évaluation : leur meilleur score natif ne se retrouve pas dans le renderer Houdini.
- Karma XPU ne tourne que sur CPU ou NVIDIA : sur une carte AMD, les rendus passent par Karma CPU.
- L'interface (étagère, panneau Studio, menu Tab) a été vérifiée en ligne de commande, pas à l'écran, pour les derniers changements.
- Windows uniquement.

## Licences

- `NOTICE.txt` d'origine : le code d'intégration y est déclaré sous **GNU GPL v3** (`LICENSE.txt`). Les ajouts de l'audit de novembre 2026 (nettoyage de floaters, raffinement par apprentissage, résolution de moteur, tests) n'ont pas reçu de licence propre : à décider avant de rendre le dépôt public.
- **Spirula Studio** (harry7557558/spirula-studio) est sous GPL v3 : il n'est pas redistribué ici.
- Houdini appartient à Side Effects Software et n'est pas inclus.
