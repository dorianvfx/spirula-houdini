# Intégrations de recherche — version 7.2

## Fonctionnalités intégrées

**Nodes 07 (Architecture) et 10 (scan + objets)** : export compressé SOG ou SPZ via SplatTransform 3.10.3, fourni avec un Node privé. Boutons de suivi et d’arrêt, fichier final atomique, PLY source figé pour le job. Aucune installation npm globale n’est nécessaire à l’utilisation.

La convention **PlayCanvas / SuperSplat** convertit l’axe vertical USD Y/Z et les unités en mètres. Le choix **Conserver les axes du PLY** garde les coordonnées brutes pour un autre viewer. Le PLY principal reste le format de travail dans Houdini ; le SOG/SPZ est un export pour un viewer qui le prend en charge.

Sur Windows/Radeon, le chemin automatique utilise WebGPU Direct3D12, avec un repli CPU en cas d’échec. Le chargement Vulkan de Dawn a échoué sur cette installation ; cela n’empêche pas le trainer Spirula de fonctionner avec son propre backend Vulkan. Les tests incluent des SH non nuls, CPU, GPU, repli et SPZ.

**Nodes d’apprentissage** : choix Standard 3DGS, Mip et 3DGUT. Les deux variantes restent en évaluation. Elles sont présentes dans le moteur Spirula ; nous avons raccordé ses implémentations existantes à Houdini, pas porté nous-mêmes les dépôts CUDA originaux. Le renderer Houdini n’est pas remplacé par ces choix. Le contrôle doit se faire dans le renderer final.

**Version de moteur** : l’exécutable officiel Spirula 2026.10.30 est fourni à côté du 2026.10.16. Il est sélectionnable dans Studio et les nodes d’apprentissage. Le choix Studio s’applique à la prochaine réouverture après sauvegarde/fermeture de la session courante. L’intégration native et l’export vers Houdini ont été testés avec 5 000 gaussiennes, redimensionnement et rattachement du panneau. Les checkpoints ne sont pas repris avec une autre projection/version par inadvertance.

## Qualification

La maison passe d’environ 280 Mo en PLY à environ 4,3 Mo en SOG, soit environ 64× plus léger. Deux vues PlayCanvas comparées au PLY donnent une erreur moyenne inférieure à un niveau sur 255 ; voir Verification_Recherche.json. Ce résultat concerne cette maison avec SH nuls, pas un ratio garanti sur tous les scans.

Les benchmarks des trois primitives utilisent 12 rendus 480×320, une caméra exclue de l’apprentissage, 8 000 itérations et un plafond de 250 000 gaussiennes. 3DGUT améliore un score natif, mais le gain n’est pas conservé dans le renderer Houdini de ce cas. Le nouveau moteur n’est pas meilleur sur ce cas. Les valeurs par défaut restent donc conservées, et aucune amélioration de qualité photo/vidéo réelle n’est annoncée sur cette base.

## Projets repérés et portages

Le registre CATALOGUE_RECHERCHE.md contient 16 projets : 2DGS, SuGaR, MILo, TopoSurfel, GOF, Frosting, AA-2DGS, DN-Splatter, Scaffold-GS, LightGaussian, Hierarchical 3DGS, Brush et les outils déjà testés.

Les portages complets de 2DGS, SuGaR, MILo et TopoSurfel ne sont pas réalisés. Il faut porter leurs opérateurs/rasterizers et gradients, pas seulement remplacer un import CUDA. Les dépôts MILo et TopoSurfel portent également des restrictions commerciales à traiter avant utilisation client. Le registre indique les sources, l’état et la voie d’adaptation proposée.

Les sources et licences des dépendances livrées sont conservées. La veille est consignée dans le projet ; aucune surveillance périodique automatique n’est créée.
