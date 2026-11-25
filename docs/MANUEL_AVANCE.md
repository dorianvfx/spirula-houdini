# Spirula Studio natif dans Houdini — version 3.2

Cette version héberge **la véritable application Spirula Studio** dans un panneau Houdini : son renderer GPU, sa navigation, ses menus, ses outils de sélection, son édition, son entraînement et ses exports. Le rendu reste produit par Spirula ; l’interface n’est pas une imitation ni un flux vidéo.

Configuration visée : **Windows, Houdini 22.0.368 / Python 3.13 / PySide6**, moteur officiel Spirula Studio **2026.10.16 Vulkan**, non modifié. Le package est installé sur ce PC.


## Suivi des calculs

Spirula Insert Lit Object ouvre maintenant un suivi non modal dès le clic : étape, progression Karma, images partielles, itérations Spirula, temps, CPU/RAM et journal en direct. Le splat est annoncé chargé seulement après vérification de sa géométrie. Les états sont aussi visibles en haut des paramètres et sur le nœud. Voir `SUIVI_DES_CALCULS.md`, notamment pour activer la mise à jour à chaud avec `scripts/update_live_monitor.py` en conservant les workers suivis.

## Nouveau : objet éclairé par un scan, interface simplifiée

Sélectionner un mesh et un décor GSplat, puis **Spirula Insert Lit Object**. L’outil demande les deux sources, propose un aperçu Karma dans Houdini, génère le splat de l’objet depuis les rendus et exporte décor + objet. Il utilise le scan comme champ de radiance spatial visible aux rayons indirects de Karma XPU, avec le headlight désactivé. Il adapte les cadrages, recentre les coordonnées et restaure le placement de sortie. Un mode façade tuilé est proposé pour les grandes géométries avec précision cible et limite de vues.

Les scripts de création sont `scripts/insert_selected_object.py` et `scripts/setup_tommy_kitchen.py`. Ils s’exécutent dans Houdini. `RECHERCHE_ECLAIRAGE_SCAN.md` détaille le choix, les références et les limites : HDR écrêté non récupéré, matériaux XPU compatibles nécessaires, nouvelles ombres sur le scan non automatiques. L’outil générique Render to Splat reste disponible pour les scènes éclairées autrement.

## Ouvrir le Studio

- Dans Houdini, **Tab → Spirula Studio** crée le SOP et ouvre automatiquement le Studio dans un onglet de la zone de travail.
- Sur un nœud existant : **Projet → Ouvrir le viewport Spirula Studio**.
- Pour ouvrir directement une nouvelle instance Houdini avec le Studio : double-cliquer **Ouvrir_Spirula_Houdini.cmd**.

Si Houdini était déjà ouvert pendant la mise à jour, le redémarrer pour charger les nouveaux modules et le HDA.

Le splat coloré fourni est une démonstration synthétique de 5 000 gaussiennes. **Ouvrir…** permet de choisir un splat, des photos, un dataset ou une vidéo. Les menus et panneaux dans la grande zone centrale sont ceux du Studio original. Utiliser notamment **Modifier** pour les sélections et transformations, et les outils natifs pour reconstruire les caméras, entraîner ou générer un mesh.

Le Studio est un onglet Houdini normal : il peut être déplacé vers un autre groupe d’onglets. Le menu **⋯ → Vue côte à côte avec Houdini** place la scène Houdini à gauche et le Studio à droite. **⋯ → Détacher / Réintégrer** permet aussi de sortir ou de remettre sa fenêtre dans le panneau.

## Studio → Houdini

1. Ouvrir ou entraîner le modèle dans le Studio intégré.
2. L’éditer avec ses outils habituels.
3. Cliquer **Envoyer vers Houdini**, dans la barre supérieure du panneau.

Après un entraînement terminé (écran train/done), le bouton récupère directement le dernier checkpoint du dataset actif : il fonctionne désormais sans ouvrir le mode édition. Pour un modèle en cours d’édition, le bouton utilise la fonction native **Enregistrer une copie** de Spirula. Une nouvelle sortie est écrite dans `Dossier de travail/studio/session_.../houdini_....ply`, puis chargée automatiquement dans le SOP Spirula lié. La sélection de points, les suppressions et le placement que Spirula enregistre sont donc pris en compte par son propre exporteur, y compris les harmoniques de couleur.

Lorsqu’un modèle est déjà en mode édition, c’est celui-ci qui est envoyé. Si plusieurs modèles sont ouverts sans édition active, ouvrir **Modifier** sur le modèle voulu avant de cliquer Envoyer. Terminer les calculs et fermer les dialogues ouverts avant l’envoi.

Les splats sont convertis avec le SOP natif **Bake GSplats**. On peut ensuite ajouter les SOP habituels, modéliser des objets par-dessus dans la scène Houdini, ou importer la sortie dans Solaris/Karma XPU. **⋯ → Cadrer le splat dans Houdini** recentre le viewport Houdini sur la sortie.

L’envoi est une copie à un instant donné : les modifications encore en mémoire dans le Studio ne sont pas transmises à chaque image. Cliquer à nouveau Envoyer pour actualiser la scène.

Les scènes de démonstration sont dans `examples/` :

- `Spirula_Demo.hip` : splat, cube polygonal et mesh de collision.
- `Spirula_Studio_Natif.hip` : exemple issu d’une véritable édition dans le Studio intégré, puis envoyé dans Houdini.

## Houdini → Studio

Sélectionner le SOP dont on veut examiner la sortie, puis cliquer **Houdini → Studio**. Sans SOP sélectionné, la sortie du nœud Spirula lié est utilisée. Une copie PLY est exportée puis ouverte dans le Studio. Pour les meshes, le PLY conserve la géométrie et les couleurs compatibles ; les matériaux Houdini ne sont pas transférés.

Les échanges portent sur les coordonnées SOP. Les transforms de placement du SOP Spirula sont incorporés lors de leur ouverture et remis à l’identité après le retour d’un splat, afin d’éviter d’appliquer deux fois le déplacement. Les transforms au niveau objet Houdini restent séparés.

Les deux moteurs gardent leurs scènes respectives : les objets ajoutés dans Houdini ne sont pas injectés automatiquement dans le renderer de Spirula. Pour les afficher ensemble, utiliser le viewport Houdini, ou envoyer explicitement la géométrie souhaitée au Studio.

## Fichiers et sessions

Le PLY initial et les modèles PLY ouverts avec le bouton **Ouvrir…** sont copiés dans le dossier de session avant édition. Les échanges automatiques n’écrasent pas leurs originaux. Les OBJ/GLTF sont ouverts à leur emplacement afin que leurs fichiers de matériaux et textures relatifs restent accessibles ; leur commande native Enregistrer fonctionne comme dans Spirula autonome.

Les préférences du Studio intégré sont séparées, dans `Dossier de travail/studio/preferences`. Ses dialogues de fichiers sont configurés en mode interne pour rester utilisables dans le panneau. Les opérations lourdes et les commandes d’échange ne font pas attendre le thread d’interface Houdini.

Fermer l’onglet du panneau conserve le processus et le travail du Studio pendant la session Houdini ; rouvrir le panneau récupère la même session. **⋯ → Fermer Studio…** demande une fermeture normale à Spirula et laisse ses propres demandes d’enregistrement fonctionner. Si Houdini se ferme normalement alors que Studio reste ouvert, l’intégration tente de lui rendre une fenêtre autonome. Un arrêt brutal ou un crash ne permet pas de garantir la récupération d’éditions non enregistrées : conserver les sauvegardes natives pour le travail important.

Un Studio natif est partagé par les panneaux de la même instance Houdini. Ouvrir un deuxième panneau déplace le même Studio vers ce panneau, plutôt que de charger plusieurs renderers. Le menu **Lier au nœud Spirula sélectionné** change le SOP destinataire des envois.

## Mesh et collisions

Les gaussiennes seules ne définissent pas une surface solide. Utiliser le meshing natif de Spirula ou l’onglet **Mesh / collisions** du SOP pour générer et importer une géométrie de collision. Les sorties PLY de mesh peuvent aussi être envoyées depuis le panneau. Pour un mesh dont le format de sauvegarde natif est OBJ/GLTF, choisir PLY dans le panneau d’enregistrement Spirula avant l’envoi automatique.

Le champ **SOP de collision** du nœud indique la sortie à utiliser dans les simulations. La qualité et l’étanchéité dépendent de la reconstruction : contrôler la surface avant les simulations exigeantes.

## Automatisation et exports du SOP

Les contrôles de la première intégration restent disponibles dans les paramètres du SOP :

- vidéo → extraction d’images ;
- photos → SfM → entraînement → import automatique ;
- entraînement seul sur les caméras existantes ;
- meshing et import de collision ;
- export PLY standard ou BGEO ;
- import Solaris ;
- outils avancés Spirula avec arguments JSON et journal.

Le suivi Web de ces entraînements CLI est disponible via **Afficher le suivi de l’entraînement** ; le Studio natif reste l’interface principale pour le travail interactif.

L’export PLY du SOP prend en charge les attributs 3DGS standards et les harmoniques jusqu’au degré 3. Les formats et extensions propres à Spirula doivent être exportés depuis le Studio natif. BGEO conserve les attributs Houdini. Le réglage sRGB → linéaire est activé par défaut ; l’adapter aux sources HDR/ACEScg ou déjà linéaires.

## Objets, composition et visites architecturales

Depuis la sélection Houdini, utiliser la shelf **Spirula** ou le menu **Outils Houdini** du panneau. Les quatre SOP sont aussi disponibles avec Tab :

| Outil | Utilisation |
|---|---|
| Spirula Object to Splat | Conversion directe d’un mesh texturé, sans entraînement. Les cellules de surface suivent la précision demandée. |
| Spirula Render to Splat | Scène éclairée → images EXR et poses exactes → entraînement Spirula → splats Houdini. Méthode recommandée pour l’architecture. |
| Spirula Assemble Splats | Référencer plusieurs sorties de splats, composer en coordonnées monde et exporter un PLY complet. |
| Spirula Cut Splats | Retrait non destructif dans une boîte manipulable pour remplacer un élément scanné. |

La conversion directe prend les couleurs/textures diffuses compatibles. Elle ne reproduit pas le rendu complet des matériaux, normal maps, réflexions ou lumières de Houdini. Pour ces effets, passer par les rendus.

### Rendus photoréalistes

1. Sélectionner le mesh source puis **Spirula Render to Splat**. Pour Solaris, sélectionner le LOP final. Conserver les shaders, les textures et les lumières de la scène. Les trois lumières studio facultatives sont surtout destinées aux objets isolés.
2. Choisir **Karma CPU · OBJ** pour une scène OBJ, ou un renderer Solaris pour un stage USD. Un ROP existant peut apporter ses réglages avancés ; le worker lui impose caméra, dimensions, sortie et échantillonnage. Le ROP original est conservé dans la scène interactive.
3. Dans Caméras, utiliser un tour d’objet pour un meuble isolé ; pour une visite, **Parcours intérieur**, une courbe SOP ordonnée et une hauteur d’œil. Répartir les points dans toutes les pièces et autour des obstacles. Des caméras OBJ/USD existantes ou animées sont également utilisables. Les images indiquées dans la plage représentent des poses : le décor et sa lumière restent figés à l’image de capture.
4. **Afficher les repères des caméras** crée les frustums dans le viewport, exclus des rendus. Vérifier les angles morts, les passages, le sol, le plafond et l’arrière des objets. Actualiser les repères après un changement de paramètres.
5. Choisir un préréglage puis **Tester une image**. Utiliser **Ouvrir le dossier des rendus et journaux** pour examiner son PNG et son EXR. Ajuster la lumière, l’exposition et le cadrage avant de calculer toutes les vues.
6. **Rendre les vues puis entraîner le splat** travaille en arrière-plan et charge le résultat dans le SOP. Le statut donne le dossier, le progrès et les erreurs. Les journaux détaillés sont `worker.log` et `training.log`.
7. Sélectionner ce résultat et le splat du décor, puis **Spirula Assemble Splats**. Exporter la composition avec son bouton dédié.

| Profil intérieur | Positions × directions × angles verticaux | Résolution | Budget d’échantillons/pixel Karma (adaptatif) | Itérations | Plafond gaussiennes |
|---|---:|---:|---:|---:|---:|
| Aperçu technique | 6 × 6 × 3 = 108 | 512² | 4 échantillons/pixel | 2 000 | 300 000 |
| Architecture haute qualité | 12 × 8 × 3 = 288 | 1536² | 144 échantillons/pixel | 30 000 | 4 millions |
| Production détaillée | 24 × 8 × 3 = 576 | 2048² | 576 échantillons/pixel | 40 000 | 4 millions |

Ces nombres sont des points de départ, pas une garantie de qualité. Adapter la couverture à la taille du logement et la densité aux détails. Augmenter d’abord la couverture et la qualité des rendus si les images ne montrent pas correctement une surface. Un grand nombre de gaussiennes ne répare pas des angles morts ou du bruit dans les images. Le profil production peut demander beaucoup de temps CPU, de stockage et de mémoire. La quantité de vues exacte figure dans **Capture prévue** après le préréglage ou l’affichage des repères. Les six petites vues des tests de validation servent uniquement à vérifier la chaîne technique.

Les EXR linéaires sont conservés. Par défaut, les PNG utilisent la configuration OCIO de Houdini et une vue ACES 2.0 SDR si disponible, avec une exposition identique pour toutes les vues. Les champs OCIO permettent d’imposer une autre transformation. Pour un hébergement Web classique, utiliser les PNG/LDR. L’option EXR/HDR lit les images linéaires Rec.709 ou ACEScg et produit des splats linéaires Rec.709 et demande un lecteur compatible avec ce mode de couleur.

Chaque calcul possède un snapshot HIP, les poses exactes, un `job.json`, les images, les journaux et les checkpoints. **Reprendre** réutilise les images valides et le dernier checkpoint complet ; modifier les paramètres du nœud puis démarrer un nouveau job pour changer la capture. **Arrêter** attend la fin du rendu courant ; pendant l’apprentissage, il arrête le processus et conserve les checkpoints déjà écrits. Si Houdini a été fermé, sélectionner le `job.json` dans le champ du nœud puis Reprendre. Les dépendances externes du HIP (textures, USD, caches) doivent rester accessibles ; le snapshot n’est pas une archive de ces dépendances.

L’initialisation peut utiliser un SOP mesh : 100 000 points de surface amorcent l’apprentissage en coordonnées monde. Les caméras étant déjà connues, aucune estimation SfM n’est nécessaire. Sans seed explicite, Spirula utilise son initialisation native.

**Éclairage capturé :** le splat obtenu contient l’apparence sous l’éclairage de capture. Changer la lumière après coup demande de recalculer les vues et réentraîner. Les réflexions/verres restent une approximation dépendante des vues et des harmoniques de couleur. Un élément entraîné seul sur fond transparent ne contient pas son ombre portée sur la cuisine : pour une ombre physiquement cohérente, rendre le décor de réception avec l’objet et composer la zone concernée. Le retrait d’un frigo scanné ne recrée pas le mur occulté ni ses anciennes ombres ; prévoir une reconstruction de cette zone.

Les transformations de la composition appliquent explicitement positions, covariances et harmoniques. Cela conserve les tailles et orientations des splats, y compris avec des échelles objet non uniformes. Un Transform/Object Merge générique de Houdini peut ne pas actualiser tous ces attributs : privilégier les transforms OBJ puis l’assemblage pour l’export.

Karma CPU OBJ et Solaris ont été testés réellement sur ce PC. Le test XPU s’est exécuté avec le périphérique CPU ; ne pas compter sur un rendu Karma XPU accéléré par la Radeon. L’apprentissage Spirula utilise Vulkan sur la Radeon. Mantra reste proposé lorsqu’une licence appropriée est disponible ; la licence présente n’a pas permis de valider ce renderer.

## Installation et sources

`Install.ps1` installe le package `Documents/houdini22.0/packages/spirula-studio.json`, qui référence ce dossier complet. Après un déplacement du dossier, relancer le script puis redémarrer Houdini. Retirer ce fichier de package pour désactiver l’intégration.

Les modules sont dans `python3.13libs`, le panneau dans `python_panels`, et le générateur du HDA dans `scripts/build_assets.py` (à exécuter avec `hython`). Le module `spirula_native.py` héberge uniquement les fenêtres des processus que cette intégration lance. Il utilise les fenêtres étrangères de Qt sous Windows et l’API locale du Studio, avec un jeton propre à la session.

Le renderer et tous les contrôles restent dans l’exécutable officiel, non modifié. Les sources correspondant au moteur sont incluses dans `Spirula_Upstream_Source_v2026.10.16.zip`. Voir `LICENSE.txt` et `NOTICE.txt`.

Références : [Spirula Studio](https://github.com/harry7557558/spirula-studio), [fenêtres étrangères Qt](https://doc.qt.io/qt-6/qwindow.html#fromWinId), [conteneur Qt](https://doc.qt.io/qt-6/qwidget.html#createWindowContainer), [Bake GSplats](https://www.sidefx.com/docs/houdini/nodes/sop/bakegsplat.html).

## Vérification

`Verification.json` contient les tests de la première intégration. `Verification_Studio_Natif.json` contient les tests du panneau natif : hébergement dans la véritable interface Houdini, renderer actif, redimensionnement, édition native, copie PLY vers le SOP et réintégration de la fenêtre. Le rendu de test est fourni dans `Apercu_Studio_Natif.png`.

Les tests v3 sont consignés dans `Verification_Workbench.json` : retour après entraînement, transformation des splats, assemblage, retrait, rendus Karma, apprentissage depuis les rendus, HDR, reprise et repères caméra. Les apprentissages courts valident le fonctionnement et ne constituent pas une validation de qualité photoréaliste finale. Le HDA des nouveaux outils se reconstruit avec `scripts/build_workbench.py`.

Réglage des échantillons : [documentation officielle Karma](https://www.sidefx.com/docs/houdini/solaris/kug/sampling.html).
