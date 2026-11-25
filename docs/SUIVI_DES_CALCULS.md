# Suivi visible des calculs Spirula

Le suivi s’ouvre automatiquement lorsque vous cliquez Aperçu, Générer, Reprendre ou Exporter. Il est parenté à Houdini et reste non modal : vous pouvez continuer à travailler. Le bouton **Ouvrir le suivi en direct**, en haut du nœud, le retrouve à tout moment.

Il affiche :

- la préparation de la demande dès le clic ;
- le chargement de la scène et la construction du champ lumineux ;
- l’image Karma actuelle, le nombre d’images terminées et son pourcentage réel ;
- un aperçu partiel mis à jour par les snapshots de Karma, puis les images terminées ;
- les itérations de l’apprentissage Spirula ;
- le temps écoulé, les processus du job et leur consommation CPU/RAM ;
- les journaux du worker, de Karma et de Spirula dans un onglet ;
- la finalisation du worker, puis l’import vérifié du splat dans Houdini ;
- les erreurs explicites, avec conservation des calculs pour une reprise.

Quand une étape ne fournit pas de pourcentage, la barre reste animée : aucun faux pourcentage global ni ETA n’est inventé. Le CPU affiché est la consommation de la famille du worker ramenée au total de la machine, pas une mesure du GPU. Les nouvelles images partielles sont strictement séparées du dataset d’apprentissage.

Les paramètres État, Étape actuelle, Progression et Temps écoulé sont placés en haut du nœud. Un commentaire d’état est visible dans le réseau. Les paramètres de capture et les boutons de lancement sont désactivés pendant un job afin d’éviter des clics sans effet ou des demandes simultanées. **Arrêter** attend la fin de l’image en cours ; masquer le suivi laisse continuer le calcul.

Le viewport 3D garde la scène Houdini pendant les calculs externes. Le rendu évolue dans le suivi ; le splat remplace le mesh à l’affichage une fois l’apprentissage et l’import terminés.

## Activer la mise à jour sans redémarrer Houdini

Dans **Windows → Python Shell**, exécuter :

```python
import hou; exec(open(hou.text.expandString('$SPIRULA_ROOT/scripts/update_live_monitor.py'), encoding='utf-8').read())
```

Le script recharge l’interface et les définitions des outils, conserve les handles des workers suivis et ouvre le suivi du nœud sélectionné ou des jobs actifs. Il ne relance pas leur entraînement. Pour un job démarré avec l’ancienne version du worker, les images terminées, l’étape et l’activité restent visibles ; les snapshots partiels et le pourcentage interne Karma s’appliquent aux nouveaux jobs.

Sans job en cours, redémarrer Houdini charge également cette version. Les fichiers de votre scène et les caches ne sont pas écrasés par le script d’activation.

## Validation

`Verification_Suivi.json` consigne un vrai test dans l’interface Houdini : aperçu partiel, pourcentage Karma, CPU/RAM, itérations, import final de 98 845 gaussiennes et affichage du suivi. Ce petit entraînement sert à tester l’interface. Un second test vérifie le rechargement des contrôleurs en conservant un handle de processus de test, puis l’import d’un résultat réel existant. Les réglages production restent inchangés.

Référence des snapshots et de la sortie ALF : [documentation SideFX husk](https://www.sidefx.com/docs/houdini/ref/utils/husk.html).
