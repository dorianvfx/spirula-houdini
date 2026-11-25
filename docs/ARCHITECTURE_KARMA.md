# Mise à jour 7.3 — raffinement local après le splat

Quatre étapes dans le même réseau : **06A Zone → 06B Images de détail → 06C Raffinement → 06D Avant/Après et validation → 07 Export**. Reprise depuis un PLY existant avec scène Karma/mesh connu, ou photos et caméras Nerfstudio/COLMAP. Le splat hors zone est conservé. Voir [RAFFINEMENT_LOCAL.md](RAFFINEMENT_LOCAL.md) et Verification_Raffinement.json pour l’utilisation et les limites.

---

# Mise à jour 7.2 — export web et méthodes de recherche

Export SOG/SPZ disponible dans les nodes 07 et 10, avec suivi et conversion des axes pour PlayCanvas. Mip, 3DGUT et un moteur récent sont sélectionnables en évaluation ; les défauts sont conservés. Voir RECHERCHE_ET_COMPATIBILITE.md, CATALOGUE_RECHERCHE.md et Verification_Recherche.json pour distinguer les fonctions intégrées des portages encore à réaliser.

---

# Mise à jour 7.1 — maison propre et surfaces connues

La livraison actuelle est dans **Livraison_Maison/** : ouvrir **Maison_Splat_Propre.hip**, avec **Maison_Exterieur.ply** à côté. Elle utilise 120 vues 1024×768 et environ 1,13 million de gaussiennes. Les anciens fichiers Maison_Splat_Test / Convergence restent des expériences, pas la livraison.

Le node **05** propose maintenant deux méthodes : **apprentissage libre Spirula**, ou **mesh connu · radiance sur surfaces**. Ce second mode conserve la géométrie et transfère les couleurs des EXR Karma avec un contrôle de visibilité. Les itérations ne s'appliquent qu'à l'apprentissage libre. L'éclairage est cuit ; les reflets dépendants de la vue ne sont pas appris dans ce mode. Les surfaces non capturées sont exclues. Les paramètres de dimensions viennent toujours de la scène USD.

Les doublons issus de sélections USD recouvrantes sont retirés avant l'échantillonnage ; les instances distinctes sont conservées. Les caméras OBJ de détail sont correctement reconnues en perspective.

Voir **Livraison_Maison/LIRE_MOI.md** pour ouvrir et régénérer le résultat.

---

# Scène Karma → Gaussian Splat — Architecture

Ouvrir **Maison_Exterieur.hip** pour travailler sur la petite maison. La scène est inspirée de la référence : plain-pied, bardage gris, porche et menuiseries claires, toiture sombre, terrain et végétation simples. Les fenêtres sont des surfaces de démonstration ; aucun intérieur détaillé n’est modélisé.

Ouvrir **Maison_Splat_Test.hip** pour examiner le splat déjà calculé. Il vient d’un test court : 12 vues 480×320, 2000 itérations, environ 110 000 gaussiennes. Ses artefacts sont visibles ; ce fichier valide la chaîne et ne représente pas une livraison photoréaliste. L’aperçu Karma a un ciel transparent, ce qui est volontaire pour cet asset.

## Le réseau, dans l’ordre

| Étape | Travail |
|---|---|
| 01_SCENE_KARMA | Référence au LOP final de la scène complète, cible USD à cadrer et dossier du projet. |
| 02_CAMERAS_EXTERIEUR | Orbites ou façades par précision, avec repères visibles et caméras de détail facultatives. |
| 03_APERCU_KARMA | Rendre une vue avec les matériaux/lumières de la scène, la vérifier, puis valider. |
| 04_RENDUS_KARMA | Rendre le dataset complet, sans apprentissage automatique caché. |
| 05_APPRENTISSAGE_SPIRULA | Apprendre ou reprendre depuis les images 04, dans un dossier séparé. |
| 06_SPLAT_HOUDINI | Contrôler le splat chargé dans le viewport ; informations numériques via le bouton de contrôle. |
| 07_EXPORT_SPLAT | Exporter en PLY autonome. Le module ne publie rien sur Internet. |

Les boutons Étape suivante sélectionnent le prochain nœud. Les boutons de suivi montrent les images, les journaux et la progression dans Houdini. Les rendus se font via Karma XPU ; sur cette Radeon le périphérique CPU Embree est utilisé. Spirula utilise Vulkan pour l’apprentissage.

## Modifier la démonstration

- Géométrie : `/obj/MAISON_DEMO/MAISON_PROCEDURALE`, avec largeur, profondeur et hauteur réglables.
- Matériaux : `/stage/MAISON_MATERIAUX`, avec couleurs simples et shaders USD Preview Surface compatibles Karma.
- Éclairage : `/stage/SOLEIL_ET_CIEL`, intensité du soleil et du ciel.
- Scène finale : `/stage/OUT_SCENE_MAISON`.
- Conversion : `/obj/SPIRULA_ARCHITECTURE`, un unique Geo contenant toute la chaîne de pilotage.

La géométrie source reste dans son Geo de modélisation. Son affichage OBJ est désactivé pour éviter de doubler l’aperçu USD, mais le SOP et Solaris restent éditables. Les rendus prennent la scène Solaris originale ; ils ne reconstruisent pas ses matériaux depuis la géométrie SOP.

## Utiliser une autre maison

1. Préparer son LOP final avec géométrie, matériaux et lumières Karma.
2. Le sélectionner puis lancer **Tab → Spirula Scene Karma**, ou ouvrir **Pipeline_Architecture_Vide.hip**. Le shelf Spirula contient aussi cette entrée après ouverture d’une nouvelle session Houdini.
3. En 01, indiquer le **LOP final** et les **chemins USD du bâtiment à cadrer**. Par exemple `/World/Villa` ou `/ClientSite/Batiment_A`. Ces chemins servent au calcul des dimensions ; ils ne masquent pas le reste de la scène au renderer.
4. Exclure de la cible de cadrage le ciel, un terrain immense et les bâtiments voisins. Le rendu peut les conserver comme contexte. Le champ Primitives affichées / graines règle seulement l’aperçu SOP et l’initialisation géométrique ; `*` couvre la géométrie de la scène.
5. Choisir un dossier propre au client. Cliquer Vérifier la scène et le budget.
6. En 02, afficher les caméras et inspecter les vues de toutes les façades, du toit et du porche. Ajouter des caméras OBJ ou USD normales en perspective pour les zones cachées. Les caméras décentrées ne sont pas prises en charge.
7. Vérifier l’aperçu en 03, valider, puis lancer séparément 04 et 05. Contrôler le déplacement en 06 avant 07.

Les caméras sont calculées depuis les limites USD mondiales et le format d’image, avec les axes Y ou Z et les unités déclarées par le stage. L’orbite n’utilise aucune largeur de maison fixe. Le mode Façades règle un détail en mètres/pixel et refuse les demandes dépassant la limite de vues. Le Geo de pilotage doit garder sa transformation identité ; placer la maison dans la scène Solaris.

Pour un bâtiment très vaste, utiliser les façades par précision ou plusieurs cibles/chaînes. La couverture automatique d’une boîte englobante ne prouve pas que les renfoncements ou les côtés masqués par la végétation sont visibles. Cette version est orientée extérieur ; le parcours intérieur guidé n’est pas exposé dans ce réseau.

## Rendu, reprises et changements

Par défaut : 72 vues, 1024×768, budget d’échantillonnage 8², 30 000 itérations et plafond de 3 millions de gaussiennes. Ce sont des réglages de départ à valider selon les détails et le viewer cible.

Si la scène possède déjà des Render Settings USD particuliers, indiquer leur chemin en 01. Dans ce mode, leur qualité de rendu est conservée ; le réglage d’échantillonnage 04 ne remplace pas les paramètres de ces settings. Le champ image et la caméra de capture restent pilotés par l’outil.

Changer la scène, les textures référencées, les caméras ou les réglages d’images invalide les résultats correspondants. Une modification de lumière impose un nouveau dataset et un nouvel apprentissage. Les métadonnées internes de session Houdini sont exclues de l’empreinte, pour éviter une invalidation injustifiée à la réouverture du HIP.

L’apprentissage 05 réutilise les images 04 par liens physiques, ou copie si nécessaire. Un dataset incomplet renvoie à 04. Les checkpoints permettent de reprendre. Les fichiers du projet restent nécessaires pour rééditer/reprendre ; conserver les textures et autres dépendances de la scène source. Le PLY exporté est autonome en apparence, pas en édition.

Le rendu et l’apprentissage sont recentrés numériquement près de la cible puis replacés dans le monde à l’import. Cela préserve les transformations de scène, y compris les sous-arbres USD à reset de transform. Des coordonnées de sommets déjà imprécises dans le fichier source ne peuvent pas être réparées par ce recentrage.

## Ce qui est validé

- Rendu réel avec matériaux et lumière de la petite maison ; apprentissage réel puis import et export.
- Rendus et apprentissage séparés ; les images ne sont pas recalculées au lancement de l’apprentissage.
- 48 configurations de cadrage : proportions, échelles, grandes coordonnées, Y/Z et images portrait/paysage. Tous les coins de la cible restent dans le champ en orbite.
- Une seconde scène sans dépendance à la démo, avec un autre chemin USD et un bâtiment de 100 unités de large loin de l’origine.
- Restauration de l’origine mondiale vérifiée numériquement ; changement d’éclairage détecté ; empreinte conservée après réouverture.
- Un rendu du splat depuis une vue non utilisée pour le test. Les artefacts de ce court apprentissage restent visibles ; aucune qualité de production n’est certifiée.

Le verre, les miroirs, les détails fins, les très grandes propriétés et les matériaux non compatibles Karma nécessitent des vérifications particulières. Un splat standard conserve une apparence cuite ; il ne remplace pas les matériaux et lumières éditables du projet Houdini.
