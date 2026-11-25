# Moteur Spirula (non inclus)

Le moteur de Spirula Studio n'est **pas** dans ce dépôt : ce sont des exécutables de plusieurs centaines de Mo, sous licence GPL v3.

Le code attend :

```
runtime/spirula.exe                      moteur « stable »
runtime/versions/<version>/spirula.exe   moteurs « candidats » (la plus haute version est choisie)
```

## Récupérer la version testée (2026.10.30)

- Source : https://github.com/harry7557558/spirula-studio/releases/tag/v2026.10.30
- Fichier : `spirula-2026.10.30-windows-vulkan-x86_64.zip`
- SHA-256 attendu : `dfaf1376ab78acf4bfbaaeb7a3f12b7c06ab30bf1d9eee6082100dbc1e7b71dd`
  (voir aussi `third_party/Spirula_2026.10.30_PROVENANCE.json`)

Vérifier l'empreinte avant de dézipper :

```powershell
(Get-FileHash .\spirula-2026.10.30-windows-vulkan-x86_64.zip -Algorithm SHA256).Hash
```

Puis copier `spirula.exe` dans `runtime/versions/2026.10.30/` **et** dans `runtime/spirula.exe` si tu n'as qu'une seule version.

## Outils d'export web (optionnel)

L'export SOG/SPZ utilise PlayCanvas SplatTransform (MIT) avec Node.js, installés dans `runtime/splat-tools/` et `runtime/node/` sur la machine d'origine. Ils ne sont pas versionnés : les versions utilisées sont dans `NOTICE.txt` (SplatTransform 3.10.3, Node.js v24.22.1).

Ce dossier est ignoré par git (voir `.gitignore`), sauf ce fichier.
