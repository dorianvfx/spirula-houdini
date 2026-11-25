# Recherche : éclairer un objet 3D depuis un Gaussian splat

## Décision et preuve sur ce PC

La méthode intégrée utilise **Karma XPU et le champ de radiance spatial du scan**. Le décor est importé en `ParticleField3DGaussianSplat`, visible aux rayons indirects, invisible aux rayons caméra. L’objet conserve ses matériaux compatibles Karma XPU. Aucune lumière de studio ou headlight n’est ajoutée. Les images de l’objet ont un fond transparent ; elles sont entraînées avec leurs poses exactes, puis le résultat est remis dans le repère Houdini avant composition avec le scan original.

Le test de contrôle est important : une sphère grise a une luminance/RGB linéaire moyenne d’environ 0,049 avec la cuisine et des pixels RGB exactement nuls sans elle. Les deux rendus ont le headlight désactivé. Le test ne confond donc pas l’éclairage du scan avec une lumière automatique du renderer. Un second test emploie le véritable Tommy texturé et traverse rendu → apprentissage → import.

## Comparaison des approches

| Approche | Intérêt | Limite / décision |
|---|---|---|
| Champ de radiance natif, rayons indirects XPU | Lumière et reflets vus depuis la surface de l’objet, variation spatiale conservée ; réutilise les données existantes | Retenu. Le rendu représente l’apparence capturée, pas une récupération des watts/lux du lieu. |
| Sonde panoramique locale → dome light CPU | Très bon moyen d’utiliser une HDRI dans un renderer classique | Approximation autour d’un point ; une seule sonde ne convient pas à tout un grand bâtiment. |
| HDRI réellement photographiée/calibrée | Meilleure référence disponible pour les intensités des sources | Nécessite des données supplémentaires, et plusieurs emplacements pour un champ de lumière variable. |
| Estimation HDR générative / inverse rendering | Peut proposer des puissances lumineuses absentes des images LDR | Estimation non unique, calculs/modèles supplémentaires ; ne pas présenter des intensités inventées comme une mesure. |

[SideFX, Karma XPU](https://www.sidefx.com/docs/houdini/solaris/karma_xpu.html) documente le rendu natif des splats, leur visibilité dans les rayons indirects, le matériel pris en charge et les limites des shaders. Sur ce PC équipé d’une Radeon, le périphérique Embree CPU de Karma XPU est utilisé ; l’entraînement Spirula utilise Vulkan.

[LightHarmony3D, 2026](https://arxiv.org/html/2603.29209v1) traite l’insertion à partir d’une illumination HDR estimée, d’une géométrie proxy et d’un compositing d’ombres. Cette séparation confirme qu’un scan LDR ne fournit pas directement des sources physiques ni des surfaces capables de recevoir de nouvelles ombres.

[GaSLight, ICCV 2025](https://openaccess.thecvf.com/content/ICCV2025/papers/Bolduc_GaSLight_Gaussian_Splats_for_Spatially-Varying_Lighting_in_HDR_ICCV_2025_paper.pdf) traite un champ lumineux HDR variant dans l’espace. Un champ HDR reconstruit pour l’éclairage et un splat de visite ordinaire sont des données différentes. L’intégration ne prétend pas implémenter GaSLight.

[SideFX, Environment Light](https://www.sidefx.com/docs/houdini/nodes/obj/envlight.html) décrit une lumière à distance infinie, orientable mais non translatable : c’est la raison pour laquelle un simple dome ne suffit pas à représenter les variations locales d’une pièce entière.

## Limites honnêtes

Les intensités surexposées/écrêtées de la capture ne peuvent pas être retrouvées exactement à partir du seul splat LDR. L’exposition proposée est un réglage de sortie cohérent entre les vues, pas une reconstruction HDR. Le splat original garde sa lumière et ses ombres capturées ; il ne reçoit pas automatiquement une nouvelle ombre portée de Tommy. Une telle ombre sur le décor demande une géométrie réceptrice et une étape de compositing/bake distincte. Le présent outil répond à l’éclairage et au rendu de l’objet, puis à sa conversion et sa composition en splat.

Pour un grand bâtiment : le champ lumineux reste spatial ; la capture adapte les cadrages et les plans de coupe à sa boîte monde. Les caméras et le scan sont recentrés pendant le rendu/apprentissage, puis le placement d’origine est restauré. Le mode façade ajoute des prises de vue par tuiles avec 30 % de recouvrement nominal. Il ne devine pas les cours intérieures, tunnels ou pièces invisibles depuis les façades : utiliser les caméras/parcours avancés pour ces zones. Une limite de vues bloque les captures irréalistes plutôt que de réduire silencieusement leur précision.
