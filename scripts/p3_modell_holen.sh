#!/usr/bin/env bash
# Holt die vortrainierten Gewichte fuer die Instanzerkennung (Kameratag P3) und prueft die Pruefsumme.
# Die Gewichte kommen NICHT ins Repo (Ziel: $RAEUMWERK_HOME/modelle, Standard $HOME/raeumwerk/modelle).
#
#   scripts/p3_modell_holen.sh
#
# Modell: torchvision Mask R-CNN ResNet-50-FPN (v1), trainiert auf COCO 2017 (91 Klassen, darunter
# "wine glass" 46, "cup" 47, "bowl" 51; keine Klasse "plate"). Code: BSD-3 (torchvision); Trainingsdaten COCO
# (Annotationen CC BY 4.0, Bilder mit Flickr-Lizenzen). Die Gewichte stehen in der offiziellen torchvision-
# Modellliste; Lizenz der Gewichte: wie torchvision (BSD-3) mit dem Hinweis, dass die Trainingsdaten COCO sind.
# Pruefsumme: die ersten 8 Hex-Zeichen stehen im Dateinamen (torchvision-Konvention), die volle SHA-256 ist hier
# beim ersten Download festgehalten (SHA256_SOLL) und wird bei jedem Lauf geprueft.
set -euo pipefail
if [ -f "$(dirname "$0")/../config/local.env" ]; then set -a; . "$(dirname "$0")/../config/local.env"; set +a; fi
RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
ZIEL=${RAEUMWERK_MODELLE:-$RAEUMWERK_HOME/modelle}
NAME=maskrcnn_resnet50_fpn_coco-bf2d0c1e.pth
URL=https://download.pytorch.org/models/$NAME
SHA256_SOLL=bf2d0c1efbc936eeee2bc95a48e80ebc86b891f61b0106485937fc29f9315fc0
mkdir -p "$ZIEL"
if [ ! -f "$ZIEL/$NAME" ]; then
  nice -n 10 curl -fL --retry 3 -o "$ZIEL/$NAME.teil" "$URL"
  mv "$ZIEL/$NAME.teil" "$ZIEL/$NAME"
fi
ist=$(sha256sum "$ZIEL/$NAME" | cut -d' ' -f1)
case "$ist" in bf2d0c1e*) ;; *) echo "Pruefsumme passt nicht zum Dateinamen (bf2d0c1e...): $ist" >&2; exit 4;; esac
[ "$SHA256_SOLL" = "$ist" ] || { echo "SHA-256 weicht ab: $ist (erwartet $SHA256_SOLL)" >&2; exit 4; }
echo "ok: $ZIEL/$NAME ($ist)"
