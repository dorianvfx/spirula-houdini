# SIGGRAPH et outils existants : recherche du 17 nov. 2026

Sources : résultats de recherche web (listes communautaires partielles, pages d'éditeurs, presse spécialisée). Aucune liste officielle complète ; rien n'a été installé ni exécuté pour cette note. Contrainte PC : Radeon RX 7800 XT (pas de CUDA).

## Articles (qualité / détail)
- SIGGRAPH 2026 : [Faster 3DGS Convergence via Structure-Aware Densification](https://dl.acm.org/action/showFmPdf?doi=10.1145%2F3799902) (densification guidée par la structure) ; VidSplat (reconstruction avec a priori de diffusion vidéo guidé par la géométrie) ; Ref-DGS (reflets proches) ; [Gaussian Point Splatting](https://momentsingraphics.de/Siggraph2026.html) (rendu, des centaines de millions de gaussiennes).
- SIGGRAPH Asia 2025 : [Spectral-GS](https://dl.acm.org/doi/10.1145/3757377.3763907) (détails hautes fréquences, gaussiennes en aiguilles), Neural Texture Splatting, GSWT.
- SIGGRAPH 2025 : 3DGS2 (entraînement plus rapide, type second ordre), SpotlessSplats (objets parasites), Drag Your Gaussian (édition).
- Listes à parcourir : [Awesome3DGS SIGGRAPH 2025](https://github.com/Awesome3DGS/3D-Gaussian-Splatting-Papers/blob/main/2025/SIGGRAPH.md), [SIGGRAPH 2026 (Kesen)](https://kesen.realtimerendering.com/sig2026.html), [SIGGRAPH Asia 2025 (Kesen)](https://www.realtimerendering.com/kesen/siga2025Papers.htm).
- Code non confirmé pour la plupart de ces articles.

## Outils déjà utilisables (surtout dans Houdini)
- **Houdini 22 natif** : nettoyage procédural de splats, rigging, relighting ; les prototypes de relighting sont sortis en nodes [SideFX Labs](https://radiancefields.com/sidefx-labs-ships-three-gaussian-splat-nodes-for-relighting-delighting-and-normal-reconstruction) (relight, delight, reconstruction des normales).
- **[GSOPs 3.0 (CG Nomads)](https://radiancefields.com/cg-nomads-adds-houdini-22-support-and-gaussian-splat-baking-in-gsops-3.0.0)** : support Houdini 22, relight IBL (accès anticipé), histogramme et nettoyage.
- **[Nodeconnector](https://radiancefields.com/nodeconnector-releases-a-free-gaussian-splat-cleanup-hda-for-houdini-22)** : HDA de nettoyage gratuit (doublons, floaters, bruit alpha, trous). Licence « Limited Commercial », incompatible Apprentice.
- **[SuperSplat](https://radiancefields.com/best-gaussian-splatting-editors)** (PlayCanvas, navigateur) : nettoyage manuel et compression à l'export.

## Entraîneurs alternatifs
- **Brush** : open source, multiplateforme ; la source indique une large compatibilité de machines, sans benchmark trouvé.
- **[LichtFeld Studio](https://radiancefields.com/platforms/lichtfeld-studio)** : MCMC, 3DGUT, grille bilatérale ; NVIDIA/CUDA requis, GPLv3.
- **[gsplat](https://github.com/nerfstudio-project/gsplat/)** (nerfstudio, Apache 2.0) : bibliothèque CUDA, densification MCMC.
- 3DGRT/3DGUT de NVIDIA (open source), déjà exposé en partie via le moteur Spirula (3DGUT).

## Recoupements avec notre travail
- Le pipeline Karma de Codex sert à convertir une scène 3D créée dans Houdini (éclairée et rendue dans Karma, en centaines de vues) en splat entraîné par Spirula, pour des visites architecturales photoréalistes ; il permet aussi d'insérer ou de remplacer des objets dans un scan. Les nodes SideFX Labs (relight, delight, normales) agissent sur un splat DÉJÀ existant : ils ne remplacent pas ce pipeline. (Une version précédente de cette note les présentait à tort comme comparables.)
- Notre nettoyeur de floaters (outil d'appoint sur un splat existant) double en partie Houdini 22 natif, GSOPs et Nodeconnector : comparer avant de le garder.
- Aucune de ces sources ne donne de gain de qualité mesuré ; ce sont des notes de version et des articles.
