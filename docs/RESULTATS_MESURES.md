# Résultats mesurés (novembre 2026)

Tout ce qui est chiffré ici a été mesuré. Les limites sont écrites à côté de chaque résultat. **Un seul scan réel a été mesuré** : un intérieur (cuisine), 390 images extraites d'une vidéo (3264×1836, 387 caméras placées, 212 930 points), entraîné en 30 000 étapes avec 1 million de gaussiennes (réglage « medium »). Matériel : AMD Radeon RX 7800 XT, moteur Spirula 2026.10.30.

Mesure de qualité : PSNR et SSIM sur **49 photos mises de côté** (1 sur 8). « cc » = après correction de couleur par photo faite par le moteur.

## 1. Correction du code (tests automatiques)

| Vérification | Résultat |
|---|---|
| Base des harmoniques sphériques degré 3 contre les constantes de référence 3DGS | écart max 2e-15 |
| Rotation des harmoniques | écart max 2e-14 |
| Transformation d'un splat (rotation, échelle ×3, échelle non uniforme) puis export PLY : covariance, positions, couleurs | tous < 2e-7 |

## 2. Nettoyage de floaters

Sur « cuisine + objet » (3 503 272 gaussiennes) :

| Réglage | Retiré | Détail |
|---|---|---|
| Premiers réglages (voxel automatique unique) | 456 313 (13 %) ; **59 % de la partie cuisine** | Faux : la cuisine était jugée « isolée » car le voxel était calé sur l'objet minuscule. |
| Réglages finaux (voxel proportionnel à la taille de chaque gaussienne, protection des opaques) | **15 786 (0,45 %)** | 7 173 quasi invisibles, 4 520 géantes, 4 093 isolées et faibles ; 0 % de l'objet. |

Sur une maison de 1,1 à 1,6 million de gaussiennes (scène synthétique) : 3 à 1 110 retirées. Limite : aucun contrôle visuel dans le viewport n'a pu être fait pour dire si ces 2 % de la cuisine sont de vrais floaters.

## 3. Raffinement par apprentissage (node *Raffiner par apprentissage*)

Splat d'origine = checkpoint à 30 000 étapes, qui **a vu** les photos de test à l'entraînement (avantage pour l'original).

| Passe | Splats | PSNR brut | SSIM brut | PSNR cc | SSIM cc |
|---|---|---|---|---|---|
| Original (demi-résolution) | 771 493 | 29,67 | 0,9522 | 32,54 | 0,9576 |
| Rapide (3 000 étapes, demi-résolution) | ≈ 1,5 M | 30,86 | 0,9537 | 32,24 | 0,9553 |
| Original (pleine résolution) | 771 493 | 29,71 | 0,9585 | 32,51 | 0,9642 |
| Standard (8 000 étapes, pleine résolution) | 2 999 681 | 30,68 | 0,9595 | 32,12 | 0,9616 |

Lecture : le gain brut (+1 dB) est surtout de la cohérence de couleur ; après correction de couleur, le raffiné est légèrement moins bon. Le PLY passe de 182 à 709 Mo. **Aucun gain démontré sur ce scan.** Un nouvel entraînement identique obtient 30,48 dB : l'écart entre deux entraînements est du même ordre que le « gain » du raffinement.

## 4. Courbe d'entraînement (nouvel entraînement, 49 photos mises de côté)

| Étapes | PSNR brut | SSIM brut | PSNR cc | SSIM cc |
|---|---|---|---|---|
| 5 000 | 29,42 | 0,9543 | 30,75 | 0,9566 |
| 10 000 | 29,91 | 0,9568 | 31,56 | 0,9594 |
| 15 000 | 30,13 | 0,9581 | 31,86 | 0,9605 |
| 20 000 | 30,26 | 0,9586 | 32,08 | 0,9610 |
| 25 000 | 30,45 | 0,9584 | 32,08 | 0,9608 |
| 30 000 | 30,48 | 0,9584 | 32,16 | 0,9608 |

La qualité sur les photos de test ne baisse pas quand on entraîne plus longtemps ; elle plafonne vers 20 000 étapes. **Limite importante** : les photos de test sont voisines des photos d'entraînement (1 sur 8 le long d'une vidéo), donc cette mesure ne détecte pas une dégradation sur des points de vue éloignés du trajet de la caméra.

## 5. Diagnostic du scan

- 387 images sur 390 placées ; la caméra se déplace réellement dans la pièce (pas seulement en pivotant) ; pas moyen entre images voisines ≈ 4 % de la profondeur médiane.
- Netteté (variance du laplacien) : 14,5 / 69 / 181 aux percentiles 5 / 50 / 95. Luminosité moyenne ≈ 71 sur 255 ; 82 images avec plus de 5 % de pixels brûlés (fenêtres).
- La netteté d'une image n'explique pas l'erreur (corrélation de rang −0,28 sur 49 vues : les vues les plus nettes sont un peu plus mal reproduites).
- Comparaison photo / rendu sur deux vues : très proches ; manquent le détail fin (joints de carrelage, texture du mur), les bords en périphérie de l'image et les reflets sur les façades brillantes.
- L'écart de 2,8 dB entre PSNR brut et PSNR cc indique que la correction de couleur compense quelque chose entre images (lumière réelle qui change, vignettage, traitement d'image de la caméra…). La cause n'est **pas** établie ; la dérive d'exposition de la caméra n'est qu'une hypothèse.

## Ce qui n'est pas mesuré

Qualité sur d'autres scans, sur des points de vue éloignés du trajet, dans le viewport Houdini ou en rendu Karma ; temps de rendu Karma ; comportement sur carte NVIDIA.
