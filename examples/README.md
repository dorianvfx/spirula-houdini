# Exemples

Les scènes d'exemple (`.hip`) et leurs fichiers `.ply` ne sont **pas versionnés** : ils contiennent des chemins propres à la machine d'origine, et certains dérivent de scans privés.

Pour retrouver un exemple :

- **Maison extérieure procédurale** : le module `python3.13libs/spirula_house_demo.py` construit une petite scène extérieure ; `Ouvrir_Architecture.cmd` ouvre l'exemple correspondant s'il existe dans ce dossier.
- **Chaîne photos vide** : l'outil **Spirula Pipeline** crée la chaîne 01 → 10 dans un nouveau fichier.
- **Reconstruire les nodes** : les scripts `scripts/build_*.py` régénèrent les fichiers `otls/*.hda` (à lancer avec `hython`).

Pour l'exemple « cuisine redéfinie » de l'audit, voir `docs/RESULTATS_MESURES.md` : il se refait avec le node *Raffiner par apprentissage* et le dataset d'origine.
