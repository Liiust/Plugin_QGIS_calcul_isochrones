# QGIS Plugin – Isochrone Calculation (IGN Géoplateforme)
A QGIS plugin that enables access to the isochrone calculation service provided by the IGN Géoplateforme (https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/calcul-isochrone-isodistance/). 
The plugin uses all available services (URL: https://data.geopf.fr/navigation/getcapabilities).
It queries `https://data.geopf.fr/navigation/isochrone` using all available service parameters and displays the results on the map. 

## Installing in QGIS
Zip the 'isochrones_ign' folder -> In QGIS: Plugins > Manage and Install Plugins > Install from ZIP.

## Architecture
```
Plugin_QGIS_calcul_isochrones/
├── dev/                     # development tools, NOT installed in QGIS
├── diagrammes/              # UML diagrams (class, sequence, use case, OLD sequence diagramm in French and use case diagram in French)
├── isochrones_ign/          # the plugin itself (the only folder installed in QGIS)
├── tests/                   # automated tests (no QGIS needed)
├── .gitignore
└── README.md
```

### `isochrones_ign/` – the plugin
| File | Main content | Needs QGIS? |
|---|---|---|
| `__init__.py` | `classFactory()`, entry point called by QGIS (imports `main` only when called) | at load time |
| `main.py` | `IsochronePlugin`: toolbar icon, menu entry, opens the dialog | yes |
| `dialog.py` | `IsochroneDialog`: PyQt form, point picking, background tasks (`QgsTask`) | yes |
| `layer_builder.py` | `add_isochrone_layer()`: loads the GeoJSON result as a styled QGIS layer | yes |
| `controller.py` | `IsochroneController`, `IsochroneResult`: form values → validated request → result | no |
| `api.py` | `IsochroneRequest`, `IsochroneResponse`, `GeoplateformeClient`, capabilities model (`Options`, `ResourceOptions`, `ConstraintSpec`), exceptions | no |
| `geo.py` | GeoJSON helpers: feature collection, bounding box, approximate area, file writing | no |
| `metadata.txt`, `icon.png` | plugin metadata and icon read by QGIS | – |

The code is split in two layers: the interface (`main`, `dialog`, `layer_builder`) is the only part that imports QGIS/PyQt, while `controller`, `api` and `geo` are pure Python, which is what makes the tests below possible without QGIS.

### `dev/` – development tools (not part of the plugin)
| File | Role |
|---|---|
| `offline.py` | Fake HTTP server (`FakeSession`, sample `CAPABILITIES`) used by the tests and by the demo mode |
| `cli.py` | Command-line interface: `python -m dev.cli capabilities`, `python -m dev.cli compute …`, `--demo` for offline use |

### `tests/` – automated tests
| File | Role |
|---|---|
| `test_core.py` | Unit tests of `api`, `geo`, `controller` and `dev.cli` (30 tests, no network, no QGIS) |
| `test_live.py` | One test against the real IGN service, skipped unless `RUN_LIVE=1` |
| `capabilities_reel.json` | Copy of a real `getCapabilities` response, used as a test fixture |

## Testing
```
python -m unittest discover -s tests -v                      # 30 tests, no network
python -m dev.cli --demo compute --point 2.3373,48.8493 --cost-type time --cost-value 10 --profile pedestrian
python -m dev.cli capabilities                    # Raw JSON from the actual service
python -m dev.cli compute --point 2.3373,48.8493 --cost-value 10 --out iso.geojson
python -m dev.cli capabilities --summary          # isochrone-compatible resources
# test against the real service : bash -> RUN_LIVE=1 python -m unittest tests.test_live -v
# for PowerShell -> $env:RUN_LIVE="1"; python -m unittest tests.test_live -v
```

## Libraries: 
    requests (optional, with a fallback to `urllib`)
    PyQt
    PyQGIS

    re (for substitutions within character strings using regular expressions)
    json
    time
    dataclasses
    urllib
    typing
    math
    os
    tempfile
    argparse
    zipfile

## List of diagrams required for the analysis:
    Use case diagram
    Class diagram
    Sequence diagram

## Test view (20-minute walk from Géodata Paris using bdtopo-valhalla)
<img width="1171" height="757" alt="image" src="https://github.com/user-attachments/assets/e21062e7-ca34-43c6-ac17-5e6c68beca5e" />



    
# Extension QGIS – Calcul d'isochrones (IGN Géoplateforme) - En français
Extension QGIS permettant d'accéder au service de calcul d'isochrones proposé par la Géoplateforme de l'IGN (https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/calcul-isochrone-isodistance/).
L'extension utilise l'ensemble des services disponibles (URL : https://data.geopf.fr/navigation/getcapabilities).
Elle interroge https://data.geopf.fr/navigation/isochrone en utilisant tous les paramètres de service disponibles et affiche les résultats sur la carte.


## Installation dans QGIS
Compressez le dossier « isochrones_ign » au format ZIP -> Dans QGIS : Extensions > Installer/gérer les extensions > Installer à partir d'un fichier ZIP.

## Architecture
```
Plugin_QGIS_calcul_isochrones/
├── dev/                     # outils de développement, NON installés dans QGIS
├── diagrammes/              # diagrammes UML (classes, séquence, cas d'utilisation, ancien diagramme de séquence en français, diagramme de cas d'usage en français)
├── isochrones_ign/          # le plugin (seul dossier installé dans QGIS)
├── tests/                   # tests automatiques (sans QGIS)
├── .gitignore
└── README.md
```

### `isochrones_ign/` – le plugin
| Fichier | Contenu principal | Utilise QGIS ? |
|---|---|---|
| `__init__.py` | `classFactory()`, point d'entrée appelé par QGIS (n'importe `main` qu'à l'appel) | au chargement |
| `main.py` | `IsochronePlugin` : icône, entrée de menu, ouverture du dialogue | oui |
| `dialog.py` | `IsochroneDialog` : formulaire PyQt, choix du point, tâches d'arrière-plan (`QgsTask`) | oui |
| `layer_builder.py` | `add_isochrone_layer()` : charge le résultat GeoJSON en couche QGIS stylée | oui |
| `controller.py` | `IsochroneController`, `IsochroneResult` : formulaire → requête validée → résultat | non |
| `api.py` | `IsochroneRequest`, `IsochroneResponse`, `GeoplateformeClient`, modèle du getCapabilities (`Options`, `ResourceOptions`, `ConstraintSpec`), exceptions | non |
| `geo.py` | Utilitaires GeoJSON : FeatureCollection, emprise, aire approchée, écriture du fichier | non |
| `metadata.txt`, `icon.png` | métadonnées et icône lues par QGIS | – |

Le code est séparé en deux couches : l'interface (`main`, `dialog`, `layer_builder`) est la seule à importer QGIS/PyQt, tandis que `controller`, `api` et `geo` sont du Python pur, ce qui permet de tester sans QGIS.

### `dev/` – outils de développement (hors plugin)
| Fichier | Rôle |
|---|---|
| `offline.py` | Faux serveur HTTP (`FakeSession`, `CAPABILITIES` d'exemple) utilisé par les tests et par le mode démo |
| `cli.py` | Ligne de commande : `python -m dev.cli capabilities`, `python -m dev.cli compute …`, `--demo` pour travailler hors ligne |

### `tests/` – tests automatiques
| Fichier | Rôle |
|---|---|
| `test_core.py` | Tests unitaires de `api`, `geo`, `controller` et `dev.cli` (30 tests, sans réseau ni QGIS) |
| `test_live.py` | Un test contre le vrai service IGN, ignoré sauf si `RUN_LIVE=1` |
| `capabilities_reel.json` | Copie d'une vraie réponse `getCapabilities`, utilisée comme jeu de test |

## Tests
```
python -m unittest discover -s tests -v                      # 30 tests, sans réseau
python -m dev.cli --demo compute --point 2.3373,48.8493 --cost-type time --cost-value 10 --profile pedestrian
python -m dev.cli capabilities                    # JSON brut extrait du vrai service
python -m dev.cli compute --point 2.3373,48.8493 --cost-value 10 --out iso.geojson
python -m dev.cli capabilities --summary          # Ressources compatibles avec l'isochrone
# test avec le vrai service : bash -> RUN_LIVE=1 python -m unittest tests.test_live -v
# pour PowerShell -> $env:RUN_LIVE="1"; python -m unittest tests.test_live -v
```

## Bibliothèques : 
    requests (optionnelle, avec une solution de repli utilisant `urllib`)
    PyQt
    PyQGIS.
    
    re (pour des substitutions dans des chaînes de caractères à l’aide d’expressions régulières)
    json
    time
    dataclasses
    urllib
    typing
    math
    os
    tempfile
    argparse
    zipfile

## Liste des diagrammes attendus pour l'analyse :
    Diagramme de cas d'utilisation
    Diagramme de classes
    Diagramme de séquence

## Visualisation d'un test (20 min à pied de Géodata Paris avec bdtopo-valhalla)
<img width="1171" height="757" alt="image" src="https://github.com/user-attachments/assets/e21062e7-ca34-43c6-ac17-5e6c68beca5e" />


