# Raffiner la sortie de Spirula — version 7.3

Le module améliore une zone après un premier splat, en réutilisant des observations de meilleure qualité. Il préserve les gaussiennes originales hors de la boîte et de sa transition. Ce développement utilise notre cuisson de radiance sur mesh connu ou le réapprentissage natif Spirula depuis un PLY. Ce n’est pas un portage de SuGaR, MILo ou 2DGS.

## Utilisation dans Houdini

Dans Architecture, le parcours s’insère entre **06 Splat** et **07 Export**. Sur un autre splat, sélectionner sa sortie SOP et utiliser **Spirula Raffinement local** dans la shelf ou le menu Tab. Le bouton du node 06 ajoute également ce parcours. Cliquer à nouveau retrouve le parcours existant.

1. **06A Zone de détail** : définir centre/dimensions ou sélectionner les points du splat. La boîte orange indique la région. Les dimensions sont en unités de scène ; précision et transition sont en mètres. Choisir le côté visible de la zone. Vérifier le budget avant de lancer.
2. **06B Images de détail** : en Karma, produire les nouveaux rendus rapprochés ; en photo, vérifier les originaux, les poses et le recouvrement avec la zone. Le suivi montre les images, la progression et les erreurs.
3. **06C Raffinement** : calculer un candidat depuis ces observations. Les images Karma existantes restent réutilisables lorsque seuls le budget ou les réglages d’apprentissage changent. Un nouvel essai crée un nouveau job ; il ne reprend pas automatiquement un ancien checkpoint photo.
4. **06D Contrôle** : choisir Avant / Après, inspecter les gros plans, les raccords et une vue oblique, puis valider le candidat. Le node 07 exporte cette sortie ; un export PLY indépendant est aussi disponible en 06D.

Modifier la zone, le mesh, les matériaux, les images ou les caméras invalide le candidat. Exporter un candidat non validé ou affiché en mode Avant est refusé. Le PLY source est conservé ; l’insertion dans Architecture change le nom d’export s’il écrasait directement ce fichier source. Pour plusieurs zones, on peut ajouter un autre parcours après la sortie déjà validée.

## Scène Karma et mesh connu

Le module utilise le LOP complet, avec ses matériaux et lumières, et le SOP polygonal de référence. Les sources sont reprises automatiquement depuis Architecture. Des vues rapprochées sont réparties par tuiles et directions légèrement obliques, selon la précision demandée et la taille de la boîte ; ce n’est pas un nombre fixe de vues pour toute une maison.

La surface est découpée à la boîte avec interpolation des sommets. Les faces cachées sont présélectionnées avant un échantillonnage sur grilles de surface, avec couverture des détails étroits. Les gaussiennes gardent la géométrie connue ; leurs couleurs viennent des EXR linéaires, avec tests de visibilité sur le mesh complet. Les échantillons sans observation sont exclus. Les gaussiennes originales d’une région sans nouveau support sont conservées.

La transition atténue les opacités en tenant compte de la transmission. Elle limite les raccords sans supprimer les splats hors zone. Les gaussiennes étendues situées juste hors zone peuvent encore déborder visuellement : adapter la boîte et sa transition.

## Photos / vidéo extraite

Choisir un dataset **Nerfstudio** contenant `transforms.json`, ou une racine **COLMAP** avec `images/` et `sparse/0/` (ou `sparse/`). Les reconstructions COLMAP texte et binaires sont reconnues. Modèles pris en charge par l’adaptateur : SIMPLE_PINHOLE, PINHOLE, SIMPLE_RADIAL, RADIAL et OPENCV. Les distorsions radiales/OpenCV sont transmises à la rectification native du moteur. Pour les autres modèles COLMAP, fournir sa reconstruction dédistordue PINHOLE. Les poses Nerfstudio avec applied_transform/applied_scale demandent une normalisation explicite en amont.

Les poses doivent être alignées au PLY. Une transformation positive de rotation/translation/échelle uniforme peut convertir le repère du dataset vers le splat ; elle est reprise automatiquement lorsque le job Houdini d’origine est disponible. Un contrôle de projection vérifie qu’au moins trois images voient la zone, sans prouver à lui seul l’exactitude de l’alignement. Le Geo de pilotage doit être à identité ; placer les transformations dans un Transform SOP avant le module.

Le trainer démarre avec tous les paramètres du **PLY existant**, et non seulement un nouveau nuage de points. La zone peut être subdivisée avant apprentissage ; les images sont utilisées à leur résolution native. Un masque de région concentre la perte, le contexte est conservé pour l’occlusion, et des mouvements plus faibles évitent de disperser inutilement la géométrie déjà reconstruite. Le masque reçoit des points issus du vrai splat, pour éviter sa construction sur des points aléatoires. Après apprentissage, seul le patch est réintégré ; le reste du splat original est conservé.

## Résultats vérifiés et limites

- Maison : 20 nouvelles vues de détail à 1024² sur la fenêtre gauche ; 484 087 nouvelles gaussiennes observées, 11 010 originales retirées, **1 109 453 gaussiennes hors zone conservées à l’identique**. Le résultat complet contient 1 600 747 gaussiennes.
- Deux caméras de contrôle indépendantes dans Karma : le PSNR de la région comparée passe de 22,84 à 23,85 dB de face, et de 23,84 à 24,35 dB en oblique. Les captures montrent des contours et vitres plus propres. Ces valeurs ne sont pas une promesse pour toutes les scènes.
- Mire synthétique multivue : reprise réelle du PLY sur Radeon/Vulkan et comparaison hors apprentissage dans PlayCanvas. Le PSNR passe d’environ 12,89 à 20,61 dB ; l’erreur moyenne d’environ 47 à 8 niveaux/255. Ce test ne valide pas encore la qualité sur de vraies photos.
- Lecture COLMAP texte/binaire, poses, distorsion OpenCV, init-PLY et rectification native testés. Annulation, fichiers tronqués, longues faces étroites, changement d’unités, comparaison, refus des résultats périmés et rechargement HIP testés.

Le module ne crée pas d’informations absentes des observations. Il ne reconstruit pas automatiquement des surfaces jamais vues, et n’est pas un upscaler génératif. Le mode Karma actuel reste une apparence statique sans apprentissage des reflets dépendants de la vue ; les tests de visibilité de surface considèrent le mesh opaque. Les vrais scans, les matériaux transmissifs, les grandes variations d’exposition et les prises de vue insuffisantes demandent des contrôles supplémentaires.

Les rapports de qualification sont fournis dans `Verification_Raffinement.json`. Les détails, le budget mémoire et le temps dépendent de la taille de la zone : réduire la région ou augmenter son budget si la précision demandée ne peut pas y tenir. Aucune baisse silencieuse de précision n’est appliquée.
