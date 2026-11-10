"""
Builds isochrones_ign.zip (with the plugin folder at the root of the zip file) for installation in QGIS. 

python package.py
"""

# Liiust

import os
import zipfile

PLUGIN = "isochrones_ign"
EXCLUDE_DIRS = {"__pycache__"}

with zipfile.ZipFile(f"{PLUGIN}.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(PLUGIN):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if not f.endswith(".pyc"):
                z.write(os.path.join(root, f))
print(f"-> {PLUGIN}.zip")


"""
## Install in QGIS
`python package.py` produit `isochrones_ign.zip` -> QGIS : Extensions > Installer/Gérer les extensions > Installer depuis un ZIP.
"""
