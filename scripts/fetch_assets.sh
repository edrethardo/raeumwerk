#!/usr/bin/env bash
# Holt die Referenzunterlagen zum ReBeL-Modell nach $RAEUMWERK_ASSETS
# (Standard $RAEUMWERK_HOME/assets) und prueft jede Datei per sha256.
# Nichts davon liegt im Repo (siehe docs/robotermodell.md):
#   * igus-Datenblatt ReBeL 6 DOF (PDF, igus-Nutzungsbedingungen, nicht
#     zur Weitergabe freigegeben)
#   * iRC_ROS (CommonplaceRobotics, Apache-2.0): ReBeL-xacro und LICENSE als
#     Vergleichsmodell fuer tests/test_rebel_kinematics.py
#   * iRC_ROS-Meshes Joint0..6.dae des ReBeL 6 DOF (Apache-2.0, Herkunft
#     der Geometrie nicht dokumentiert): Optik fuer scripts/render_video.py;
#     bewusst nicht im Repo
#
#   scripts/fetch_assets.sh            # holen + pruefen
#   RAEUMWERK_ASSETS=... pytest tests  # dann laufen die Asset-Tests
#                                      # (test_cpr_numbers_in_fetched_asset, test_visual_mesh)
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
DEST=${RAEUMWERK_ASSETS:-$RAEUMWERK_HOME/assets}

IRC_COMMIT=41701e6df3398087d217f0f478622e60f694de41
IRC=https://raw.githubusercontent.com/CommonplaceRobotics/iRC_ROS/$IRC_COMMIT
M=irc_ros/meshes/igus_rebel_6dof_00                     # Ziel unter DEST
MQ=irc_ros_description/meshes/igus_rebel_6dof_00          # Pfad in iRC_ROS
DS=https://www.igus.com/ContentData/Products/Downloads/technical%20data%20sheet%20ReBeL%206DOF_EN.pdf

# Zielpfad (relativ zu DEST) | sha256 | URL
FILES=(
  "igus/rebel_6dof_datenblatt_en.pdf|02b8d7af4a3c971ba93d29cb9cb2cd06510e1b87c2b01422bf8c0e218b12ea49|$DS"
  "irc_ros/urdf/igus_rebel_6dof_00.description.xacro|31d92942b252ae9ea8c49f885ac92ebfc452bf50750680794b113a237d1a16f8|$IRC/irc_ros_description/urdf/robots/igus_rebel_6dof_00.description.xacro"
  "irc_ros/urdf/igus_rebel_6dof_01.description.xacro|76489bd907c4d3ea7f3f1a7b50e60e4920607827a2db02e2d5383d49b030b52f|$IRC/irc_ros_description/urdf/robots/igus_rebel_6dof_01.description.xacro"
  "irc_ros/LICENSE|ffcc552b141668739a97d38f11952199a1fc155eaf81880dd5917a81a415ef9f|$IRC/LICENSE"
  # Visual-Meshes des ReBeL 6 DOF (nur Optik, rebel_model/visual_mesh.py)
  "$M/Joint0.dae|146b8890dcc0fb04f0b0a7baea138f816fab20aed94396611cf5e32739d92ad9|$IRC/$MQ/Joint0.dae"
  "$M/Joint1.dae|d85b816d0bb2c9f8ff12c33d598ce37d8b437a7c85847b4eded9e7c45b526e79|$IRC/$MQ/Joint1.dae"
  "$M/Joint2.dae|36e29bd2445700e27be8567b5eb898afa62f7890d6237a4f3ad25419dfef1f5f|$IRC/$MQ/Joint2.dae"
  "$M/Joint3.dae|b8f4d3214218a3f525d1dd376cb8d36f550f83600f7dda607fb9618cc341cc35|$IRC/$MQ/Joint3.dae"
  "$M/Joint4.dae|e097f7b797f88c73b6086a78d8c62cca29a4765aa449d5ff0c02eeb4f3eb0acb|$IRC/$MQ/Joint4.dae"
  "$M/Joint5.dae|8ae70e272209c4d79b6c48d6aeaf88974a7497caf03fd7244bdbf3298ddfb1c9|$IRC/$MQ/Joint5.dae"
  "$M/Joint6.dae|d68b1b8f0e16d34d3868039041d489e47350bb07ec6ca1119d687362f21e4f59|$IRC/$MQ/Joint6.dae"
)

rc=0
for entry in "${FILES[@]}"; do
  IFS='|' read -r rel sha url <<< "$entry"
  f="$DEST/$rel"
  mkdir -p "$(dirname "$f")"
  if [ -f "$f" ] && echo "$sha  $f" | sha256sum -c --status; then
    echo "ok (vorhanden)  $rel"; continue
  fi
  curl -fsSL --retry 3 -m 300 -o "$f.part" "$url"
  if echo "$sha  $f.part" | sha256sum -c --status; then
    mv "$f.part" "$f"; echo "ok (geholt)     $rel"
  else
    echo "sha256 FALSCH   $rel (Quelle geaendert? docs/robotermodell.md pruefen)" >&2
    mv "$f.part" "$f.falsch"; rc=5
  fi
done
echo "Assets: $DEST"
exit $rc
