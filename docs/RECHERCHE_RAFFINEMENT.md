# Raffinement de splat par apprentissage : ce qui existe (10 nov. 2026)

Objectif : ne pas repartir de zéro. Contrainte du PC : **AMD Radeon RX 7800 XT (Vulkan, pas de CUDA)**.

## Ce qu'on réutilise déjà (rien à installer)
- **Moteur Spirula 2026.10.30** : `train --init-ply` reprend un splat entraîné, garde la densification et travaille en Vulkan sur AMD. C'est la base du node « Raffiner par apprentissage » (`spirula_polish.py`).

## Pistes publiées (liens des auteurs ; vérifier licence et matériel avant d'adopter)
| Piste | Idée | Code | Compatible AMD ? |
|---|---|---|---|
| [SR-GS / SRGS](https://github.com/XiangFeng66/SR-GS) | super-résolution 3DGS à partir de vues basse résolution | oui | probablement CUDA |
| [SuperGS](https://github.com/SYXieee/SuperGS) | un modèle de super-résolution d'image sert d'a priori 2D pour guider le détail | oui | probablement CUDA |
| [S2Gaussian](https://arxiv.org/html/2503.04314v1) | photos super-résolues, puis raffinement des gaussiennes haute résolution | non confirmé | — |
| [SplatSuRe](https://arxiv.org/html/2512.02172v1) | super-résolution sélective, seulement où les gaussiennes sont sous-échantillonnées | non confirmé | — |
| [SuperGaussian (Adobe)](https://research.adobe.com/publication/supergaussian-repurposing-video-models-for-3d-super-resolution) | rendu vidéo du splat, surrésolution vidéo, puis re-splat | non confirmé | — |
| [Difix3D+](https://arxiv.org/abs/2503.01774) (NVIDIA, CVPR 2025) | diffusion à une étape qui corrige les artefacts des vues rendues | oui (nv-tlabs) | CUDA ; licence NVIDIA non commerciale pour la v1, « Fixer » commerciale |
| [GSFix3D](https://github.com/GSFix3D/GSFix3D), GSFixer, 3DGS-Enhancer | diffusion pour réparer artefacts et trous | partiel | CUDA |
| [Spectral-GS](https://letianhuang.github.io/spectralgs) (SIGGRAPH Asia 2025) | découpe adaptée aux gaussiennes en aiguilles, plus de hautes fréquences | non confirmé | — |
| [FDS-GS](https://github.com/whoiszzj/FDS-GS) | contrôle de densité par fréquence | oui | CUDA |
| [MILo](https://arxiv.org/html/2506.24096v2) | maillage dans la boucle d'entraînement | oui | CUDA |

## Ce que ça veut dire pour nous
1. **Aucune de ces méthodes ne tourne telle quelle sur la Radeon** : la plupart reposent sur CUDA. Les adopter demanderait un portage ou une carte NVIDIA.
2. **Le principe commun est réutilisable sans CUDA** : « un a priori 2D améliore les photos, puis le splat est ré-entraîné dessus » (SuperGS, S2Gaussian, SplatSuRe). Un super-résolveur d'image qui tourne sur Vulkan/AMD (par exemple Real-ESRGAN en version ncnn-Vulkan) pourrait fournir les photos améliorées, que le node actuel consommerait ensuite. Non testé ici.
3. **Limite de principe** : sans a priori génératif, rien ne remplace une photo manquante ; avec, le détail ajouté est plausible mais inventé.

Les affirmations « code disponible » viennent de résultats de recherche et ne sont pas vérifiées dépôt par dépôt.
