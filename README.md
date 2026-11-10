# QGIS Plugin – Isochrone Calculation (IGN Géoplateforme)

A QGIS plugin that queries `https://data.geopf.fr/navigation/isochrone` using all available service parameters and displays the results on the map. 

## Libraries: 
    `requests` (optional, with a fallback to `urllib`)
    PyQt
    PyQGIS

    re # (for substitutions within character strings using regular expressions)
    json
    time
    dataclasses
    urllib
    typing
    math
    os

## List of diagrams required for the analysis:
    Use case diagram
    Class diagram
    Activity or sequence diagram

## Architecture
| File | Role | Depends on QGIS? (bool) |
|---|---|---|
| `api.py` | `IsochroneRequest`, `GeoplateformeClient`, read getCapabilities/answer | FALSE |
| `geo.py` | FeatureCollection GeoJSON, area, extent, file writing | FALSE |
| `controller.py` | form -> request validated -> result | FALSE |
| `layer_builder.py`, `dialog.py`, `main.py`, '__init__.py' | QGIS layer, PyQt interface, plugin input| TRUE |

## Testing without QGIS
```
python -m unittest discover -s tests -v                      # 30 tests, no network
python -m isochrones_ign.cli --demo compute --point 2.3373,48.8493 --cost-type time --cost-value 10 --profile pedestrian
python -m isochrones_ign.cli capabilities                    # Raw JSON from the actual service
python -m isochrones_ign.cli compute --point 2.3373,48.8493 --cost-value 10 --out iso.geojson
python -m isochrones_ign.cli capabilities --summary          # isochrone-compatible resources
# test against the real service : bash -> RUN_LIVE=1 python -m unittest tests.test_live -v
# for PowerShell -> $env:RUN_LIVE="1"; python -m unittest tests.test_live -v
```

## Installing in QGIS
Zip the 'isochrones_ign' folder -> In QGIS: Plugins > Manage and Install Plugins > Install from ZIP.



    
# Extension QGIS – Calcul d'isochrones (IGN Géoplateforme) - En français

Proposer un plugin QGIS permettant de faire appel au service de calculs d'isochrones de la Géoplateforme IGN (https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/calcul-isochrone-isodistance/). 
Possibilité de paramétrer la requête (url : https://data.geopf.fr/navigation/getcapabilities) avec toutes les possibilités offertes par le service, et afficher la réponse dans l'interface cartographique.

## Bibliothèques : 
    `requests` (optionnelle, avec une solution de repli utilisant `urllib`)
    PyQt
    PyQGIS.
    
    re # (pour des substitutions dans des chaînes de caractères à l’aide d’expressions régulières)
    json
    time
    dataclasses
    urllib
    typing
    math
    os

## Liste des diagrammes attendus pour l'analyse :
    Diagramme de cas d'utilisation
    Diagramme de classes
    Diagramme d'activité ou de séquence

## Architecture
| Fichier | Rôle | Dépend de QGIS ? (booléen) |
|---|---|---|
| `api.py` | `IsochroneRequest`, `GeoplateformeClient`, lecture de `getCapabilities`/réponses | NON |
| `geo.py` | `FeatureCollection` GeoJSON, calcul de surface, emprise, écriture de fichiers | NON |
| `controller.py` | Formulaire -> validation de la requête -> traitement du résultat | NON |
| `layer_builder.py`, `dialog.py`, `main.py`, `__init__.py` | Couche QGIS, interface PyQt, point d'entrée de l'extension | OUI |

## Tests hors QGIS
```
python -m unittest discover -s tests -v                      # 30 tests, sans réseau
python -m isochrones_ign.cli --demo compute --point 2.3373,48.8493 --cost-type time --cost-value 10 --profile pedestrian
python -m isochrones_ign.cli capabilities                    # JSON brut extrait du vrai service
python -m isochrones_ign.cli compute --point 2.3373,48.8493 --cost-value 10 --out iso.geojson
python -m isochrones_ign.cli capabilities --summary          # Ressources compatibles avec l'isochrone
# test avec le vrai service : bash -> RUN_LIVE=1 python -m unittest tests.test_live -v
# pour PowerShell -> $env:RUN_LIVE="1"; python -m unittest tests.test_live -v
```

## Installation dans QGIS
Compressez le dossier « isochrones_ign » au format ZIP -> Dans QGIS : Extensions > Installer/gérer les extensions > Installer à partir d'un fichier ZIP.
