# Catalogue de recherche — 9 novembre 2026

Les sources ci-dessous sont les dépôts ou pages des auteurs. Les pistes de portage sont nos propositions d’ingénierie, pas des fonctionnalités déjà réalisées. Une méthode repérée n’est pas présentée comme installée.

## Ce qui fonctionne maintenant

- Export SOG/SPZ par PlayCanvas, avec progression dans Houdini, sortie atomique et copie du PLY source pour le job. Direct3D12 fonctionne sur la Radeon ; le chargement Vulkan de Dawn a échoué dans cet environnement, et le repli CPU a été testé. Le moteur Spirula conserve son backend Vulkan.
- Choix 3DGS / Mip / 3DGUT dans les nodes d’apprentissage. Les variantes restent en évaluation et le défaut est conservé.
- Spirula 2026.10.30 installé côte à côte, avec ses sources. Hébergement natif dans Qt, redimensionnement, rattachement et export PLY vers Houdini validés. Sélection explicite, pas de remplacement silencieux des sessions ouvertes ni de mélange des checkpoints.

## Résultats et portée

La maison de livraison n’a pas été réentraînée ni remplacée par un des modèles de recherche. Son export web compressé est ajouté à côté du PLY.

Benchmark des primitives : 12 images synthétiques 480×320 pour l’apprentissage, une caméra exclue de l’apprentissage, 8 000 étapes, plafond 250 000. Il s’agit d’un seul petit cas, pas d’une validation de captures réelles.

| Moteur | Primitive | PSNR natif (dB) | SSIM natif |
|---|---|---:|---:|
| 2026.10.16 | 3dgs | 21.513 | 0.6782 |
| 2026.10.16 | mip | 22.397 | 0.6391 |
| 2026.10.16 | 3dgut | 23.609 | 0.6795 |
| 2026.10.30 | 3dgs | 21.143 | 0.6467 |
| 2026.10.30 | mip | 22.347 | 0.6340 |
| 2026.10.30 | 3dgut | 23.015 | 0.6639 |

Attention : les premières vérifications dans le renderer Houdini donnent une fidélité moindre pour Mip et 3DGUT. Un meilleur score natif ne suffit donc pas à promouvoir une variante pour la livraison Houdini. Voir les JSON et images de chaque dossier Benchmark_*/Houdini. Le moteur récent n’améliore pas ce cas par rapport au précédent ; il reste candidat. Ses évolutions de préparation photo/vidéo restent intéressantes à tester sur une capture réelle.

La compression SOG est comparée au PLY dans le même renderer PlayCanvas et aux mêmes caméras, avec les axes adaptés. Les rapports chiffrés sont dans Compression/Rapport.json. La sélection de backend, le repli CPU, les SH non nuls et SPZ ont des tests dédiés dans Compression/Compatibility.json.

## Projets et voies d’adaptation

### [Mip-Splatting](https://github.com/autonomousvision/mip-splatting) — CVPR 2024

Anti-aliasing et stabilité lors des changements de résolution.

**État :** Exposé dans Houdini ; implémentation Vulkan de Spirula testée sur Radeon.

**Limite actuelle :** Qualité non qualifiée : le test dans Houdini est moins fidèle que le baseline.

**Piste de travail :** Intégration via moteur existant ; contrôler le rendu final, pas seulement le score natif.

### [3DGUT / 3DGRT](https://github.com/nv-tlabs/3dgrut) — CVPR 2025 / SIGGRAPH Asia 2024

Projections non linéaires et, pour 3DGRT, lancer de rayons de gaussiennes.

**État :** 3DGUT exposé et testé avec Vulkan ; 3DGRT non intégré.

**Limite actuelle :** Le gain natif observé ne se conserve pas dans le renderer Houdini de ce test.

**Piste de travail :** Garder 3DGUT en évaluation ; un renderer natif Houdini exact demanderait un portage dédié.

### [SplatTransform](https://github.com/playcanvas/splat-transform) — Outil PlayCanvas

Formats SOG/SPZ, conversion, optimisation et outils pour le web.

**État :** Installé, versions figées, export asynchrone intégré aux nodes 07 et 10.

**Limite actuelle :** SOG validé sur la maison ; SPZ et SH complets testés sur petit fixture.

**Piste de travail :** Direct3D12 sur Radeon ; repli CPU ; adaptation automatique des axes Y/Z et unités pour PlayCanvas.

### [Spirula 2026.10.30](https://github.com/harry7557558/spirula-studio/releases/tag/v2026.10.30) — Version officielle du 30 octobre 2026

Création de datasets : rejet du flou/doublons ; améliorations annoncées du trainer et des viewers.

**État :** Installé à côté du moteur actuel ; API, hébergement natif et export vers Houdini testés.

**Limite actuelle :** Disponible en évaluation ; pas promu par défaut, scores de ce cas inférieurs à la version actuelle.

**Piste de travail :** Sélection de version, isolation des checkpoints ; conservation du binaire précédent.

### [2DGS](https://github.com/hbb1/2d-gaussian-splatting) — SIGGRAPH 2024

Reconstruction de surfaces à partir de disques orientés.

**État :** Repéré ; implémentation originale non installée.

**Limite actuelle :** Aucun résultat local 2DGS original.

**Piste de travail :** Porter projection/intersection disque, gradients et pertes dans les kernels Slang ; tester forward/backward et interop.

### [SuGaR](https://github.com/Anttwo/SuGaR) — CVPR 2024

Extraction de mesh et raffinement des gaussiennes liées au mesh.

**État :** Référence étudiée ; notre bake de surfaces est distinct de SuGaR.

**Limite actuelle :** Portage complet non réalisé.

**Piste de travail :** Remplacer les extensions CUDA et ajouter un vrai raffinement lié au mesh ; ne pas confondre avec une simple initialisation.

### [MILo](https://github.com/Anttwo/MILo) — SIGGRAPH Asia 2025 / TOG

Extraction de mesh différentiable pendant l’optimisation des gaussiennes.

**État :** Documentation et dépendances examinées ; pas installé comme backend.

**Limite actuelle :** Licence du dépôt limitée à la recherche/évaluation non commerciale.

**Piste de travail :** Portage du rasterizer, de l’extraction différentiable et du rendu mesh ; la licence reste à traiter pour un usage client.

### [TopoSurfel](https://github.com/Fan-Treasure/TopoSurfel) — Annoncé SIGGRAPH Asia 2026 / TOG par le dépôt

Boucle entre surfels et mesh pour guider la reconstruction.

**État :** Repéré ; pas de code intégré au produit.

**Limite actuelle :** Licence publiée réservée à l’éducation/recherche/non-profit ; aucun test local.

**Piste de travail :** Porter le rendu différentiable mesh/surfels, l’optimisation et les dépendances CUDA ; obtenir une voie d’usage commercial adaptée.

### [Gaussian Opacity Fields](https://github.com/autonomousvision/gaussian-opacity-fields) — SIGGRAPH Asia 2024 / TOG

Extraction adaptative de surfaces depuis un champ d’opacité.

**État :** Repéré ; GOF original non installé.

**Limite actuelle :** Pas de validation GOF locale.

**Piste de travail :** Comparer au mesher natif Spirula déjà disponible ; réutiliser ses briques CPU/Vulkan avant de réécrire une chaîne complète.

### [Gaussian Frosting](https://github.com/Anttwo/Frosting) — ECCV 2024

Représentation éditable autour d’un mesh, avec une couche de gaussiennes.

**État :** Repéré ; non installé.

**Limite actuelle :** Représentation et renderer spécifiques, export PLY générique à vérifier.

**Piste de travail :** Étudier couche attachée et épaisseur variable pour détails fins ; portage des opérateurs requis.

### [AA-2DGS](https://github.com/maeyounes/AA-2DGS) — NeurIPS 2025

Anti-aliasing des surfaces 2DGS lors des changements d’échelle.

**État :** Repéré ; non installé.

**Limite actuelle :** Dépend d’un renderer 2DGS compatible.

**Piste de travail :** À traiter après un backend 2DGS de base ; pas comme un filtre de sortie arbitraire.

### [DN-Splatter / AGS-Mesh](https://github.com/maturk/dn-splatter) — Projet profondeur et normales

Guider les splats par profondeur/normales, notamment pour les scans RGB-D.

**État :** Repéré ; non installé.

**Limite actuelle :** Nos essais simples de profondeur seule ne reproduisent pas cette méthode.

**Piste de travail :** Préparer un jeu réel recalé et des masques de confiance ; transposer les pertes utiles au backend existant.

### [Scaffold-GS](https://github.com/city-super/Scaffold-GS) — CVPR 2024

Structure d’ancres et génération de gaussiennes adaptée à la vue.

**État :** Repéré ; non installé.

**Limite actuelle :** Le modèle dépendant de la vue demande un renderer adapté.

**Piste de travail :** Étudier le coût du décodage, le portage et une éventuelle cuisson vers des formats d’hébergement.

### [LightGaussian](https://github.com/VITA-Group/LightGaussian) — NeurIPS 2024

Réduire le coût et le nombre de gaussiennes en conservant l’apparence.

**État :** Repéré ; non installé.

**Limite actuelle :** SOG intégré ici est une autre compression ; ce n’est pas LightGaussian.

**Piste de travail :** Évaluer importance, élagage et distillation sur des vues de contrôle avant toute réduction automatique.

### [Hierarchical 3D Gaussians](https://github.com/graphdeco-inria/hierarchical-3d-gaussians) — SIGGRAPH 2024

Représentation hiérarchique pour scènes très vastes.

**État :** Repéré ; non installé.

**Limite actuelle :** Hiérarchie et streaming nécessitent un viewer compatible.

**Piste de travail :** Priorité pour grands bâtiments : comparer partition native Spirula, LOD web et portage hiérarchique.

### [Brush](https://github.com/ArthurBrussee/brush) — Projet Rust / WebGPU

Autre trainer multiplateforme à comparer à Spirula.

**État :** Repéré ; non installé.

**Limite actuelle :** Aucun benchmark local Brush.

**Piste de travail :** Candidat pour comparer la reconstruction photo sur AMD, sans imposer CUDA.

## Portages à poursuivre

Pour 2DGS, MILo et TopoSurfel, la suite n’est pas une installation CUDA forcée : il faut identifier les opérateurs différentiables, porter leurs calculs/gradients vers Slang-Vulkan ou une autre implémentation adaptée, puis valider le renderer et les exports. Le code actuel de notre bake de mesh n’est pas un portage de ces moteurs.

Les licences de MILo et TopoSurfel publiées par leurs auteurs limitent les usages commerciaux. Une adaptation technique conserve ces conditions sur leur code. Ces projets restent donc séparés des fonctionnalités de production tant que la voie d’utilisation n’est pas adaptée. Aucune prise de contact avec les auteurs n’a été effectuée.

Ordre proposé : jeu réel de référence et contrôle commun → reconstruction de surfaces → édition/retrait d’objets → zones révélées → hiérarchie/streaming. Réévaluer la priorité selon les défauts réellement mesurés.
