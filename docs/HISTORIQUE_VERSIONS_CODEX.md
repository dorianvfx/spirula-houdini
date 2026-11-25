# Mise à jour 7.3 — raffinement local après le splat

Quatre étapes dans le même réseau : **06A Zone → 06B Images de détail → 06C Raffinement → 06D Avant/Après et validation → 07 Export**. Reprise depuis un PLY existant avec scène Karma/mesh connu, ou photos et caméras Nerfstudio/COLMAP. Le splat hors zone est conservé. Voir [RAFFINEMENT_LOCAL.md](RAFFINEMENT_LOCAL.md) et Verification_Raffinement.json pour l’utilisation et les limites.

---

# Mise à jour 7.2 — export web et méthodes de recherche

Export SOG/SPZ disponible dans les nodes 07 et 10, avec suivi et conversion des axes pour PlayCanvas. Mip, 3DGUT et un moteur récent sont sélectionnables en évaluation ; les défauts sont conservés. Voir RECHERCHE_ET_COMPATIBILITE.md, CATALOGUE_RECHERCHE.md et Verification_Recherche.json pour distinguer les fonctions intégrées des portages encore à réaliser.

---

# Mise à jour 7.1 : conversion de mesh connu

Le node 05 de la chaîne Architecture propose **Mesh connu · radiance sur surfaces** : géométrie conservée, couleurs des EXR Karma, suivi par vue et export PLY. Les doublons USD sont retirés avant échantillonnage ; les caméras OBJ supplémentaires sont reconnues correctement. Le mode libre Spirula et le pipeline photo restent disponibles.

Cette variante vise les extérieurs statiques avec un mesh connu. Elle ne reconstruit pas les reflets variables ni les surfaces absentes des captures. Voir ARCHITECTURE_KARMA.md et Verification_Maison_Propre.json.

---

# Spirula — photos et scènes Karma

Version 7 ajoute **Spirula Scene Karma**, une chaîne SOP dédiée aux scènes entièrement 3D et éclairées dans Solaris. Voir ARCHITECTURE_KARMA.md et examples/Maison_Exterieur_Demo.hip. La chaîne photos et insertion version 6 reste disponible.

# Spirula Pipeline — version 6

Ouvrir Cuisine_Pipeline_V6.hip pour reprendre la cuisine avec Tommy. Ouvrir Spirula_Pipeline_V6.hip pour commencer par de nouvelles photos. Tout reste dans un Geo. Le raccourci du Bureau crée une nouvelle chaîne ; le bouton de remplacement de 01 ajoute ses étapes si nécessaire.

## Parcours

01 Spirula/photos → 02 orientation du scan → 02A sélection → 02B retrait → 02C estimation du fond → 02D conversion du fond en splats → 02E scan réparé → 03 objet → 04 placement → 05 éclairage → 06 caméras → 07 rendus → 08 apprentissage → 09 assemblage → 10 export.

02A–02E sont facultatifs pour un simple ajout d’objet. Sans sélection et sans réparation activée, ils conservent le scan. Dans le fichier cuisine, le frigo reste à sélectionner ; Tommy est conservé comme objet 03 de démonstration et peut être remplacé par le modèle voulu.

## Sélection et retrait

1. En 02A, cliquer **1 · Sélectionner dans le viewport**. Le viewport passe en sélection de points du scan.
2. Choisir les points avec les outils de sélection Houdini.
3. Cliquer **2 · Appliquer la sélection du viewport**. Le compteur indique combien de points sont retirés et le viewport affiche 02B.
4. **Voir uniquement les points sélectionnés** isole la sélection dans un aperçu séparé. **Afficher le scan après suppression** revient au décor nettoyé.
5. Pour protéger le mur ou le sol, utiliser **Protéger du décor dans le viewport**, sélectionner les points à conserver, puis le même bouton **2 · Appliquer**. Le champ des points protégés est soustrait au retrait.
6. Le mode **Volume orienté** reste disponible. Régler centre, taille et rotation puis afficher le scan après suppression. Le volume agit sur les centres des gaussiennes : inspecter les résidus aux bords.

Désactiver le retrait en 02B restaure les points. Une sélection par numéros dépend de l’ordre du scan : la refaire après réentraînement/remplacement de sa source. Ne pas sélectionner en profondeur sans vérifier le fond inclus.

## Réparer le fond

En 02C, régler les unités de scène : tolérance des plans, pas de la surface et rayon du voisinage. Cliquer **Estimer et afficher le fond 3D**. L’aperçu montre les surfaces proposées ; examiner leur position avant **Valider ce fond et convertir en splats**. La sortie 02E montre ensuite le décor réparé.

La méthode prolonge des murs/sols approximativement plans et interpole les couleurs voisines. Elle préserve les cellules contenant des points de fond capturés. Elle ne récupère pas une texture photographique cachée ni les détails inconnus. Les motifs complexes, reflets, anciennes ombres et surfaces non planes peuvent demander une réparation manuelle. Aucun remplacement complet du vrai frigo n’est déclaré photoréaliste par ces tests.

Si l’estimation échoue ou propose un mauvais fond, modifier SURFACE_FOND_A_MODELER (géométrie, UV et matériau), puis utiliser en 02E **Solution manuelle : convertir SURFACE_FOND_A_MODELER**. Le réglage Inclure la réparation permet de comparer avec/sans.

Changer le scan, la sélection ou les paramètres après conversion rend la réparation automatique périmée : recalculer et valider 02C, ou désactiver la réparation en 02E. Reconvertir les surfaces manuelles après modification.

## Contrôle global et caches

**Vérifier tout le pipeline**, sur 01 et sur les étapes de la chaîne, écrit diagnostic_pipeline.json dans le dossier projet et présente les points à corriger. Le contrôle vérifie notamment le scan, les sources, les matériaux et textures, le nombre de vues et un budget disque indicatif. Il ne prédit pas la durée de rendu et ne mesure pas le photoréalisme.

Les empreintes des calculs incluent désormais la topologie, les attributs et le contenu des fichiers de textures référencés. Les anciens rendus peuvent donc nécessiter un nouveau calcul après cette mise à jour. Les états et caches restent séparés entre 07 et 08.

## Validation du 9 novembre 2026

Houdini 22.0.368 charge de nouveau après le changement Windows effectué par l’utilisateur. Assets construits ; test de points protégés, retrait/restauration, estimation de fond, conversion, cache périmé et topologie réussi. Test réel à la souris : sélection d’un point parmi 4700, puis 4699 points et bonne sortie affichée, sans erreur de navigation. Chaîne cuisine/Tommy vérifiée jusqu’au PLY et à la répétition : 98968 splats d’objet, 870461 assemblés, avec un apprentissage court de validation (3 vues 96², 20 itérations).

Les vues de validation indépendantes, le calcul adaptatif des caméras, l’inpainting photographique et les nouvelles ombres reçues par le scan restent des développements futurs. Les valeurs de qualité par défaut sont un point de départ, pas une qualité garantie.

Les fichiers HIP précédents et Gaussian.hip original sont conservés. La version précédente du code est sauvegardée sous outputs/Spirula_Backups. Pour charger les nouveaux modules dans une session déjà ouverte, enregistrer son travail puis ouvrir une nouvelle session Houdini.
