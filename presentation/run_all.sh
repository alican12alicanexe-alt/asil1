#!/bin/sh
# Sunumdaki her sayiyi yeniden uretir. Depo kokunden calistirilir:
#
#     sh presentation/run_all.sh            hepsi
#     sh presentation/run_all.sh figures    sadece grafikler (kosu yok, hizli)
#     sh presentation/run_all.sh disruption sadece bozucu etki kosulari
#
# Adimlar: stats headway express convoy convoylog disruption figures
#
# Butun ciktilar presentation/results/ altina yazilir, grafikler
# presentation/figures/ altina. Hangi slaytin hangi dosyadan beslendigi
# presentation/README.md'de yazili.
set -e
cd "$(dirname "$0")/.."
R=presentation/results
G=presentation/ring
mkdir -p "$R" presentation/figures

want() { [ -z "$1" ] || [ "$1" = "$2" ]; }
STEP="$1"

# --------------------------------------------------- 1. model buyuklukleri
if want "$STEP" stats; then
  echo "== stats"
  python stats.py scenarios/ring > "$R/stats-ring.txt"
fi

# ------------------------------------ 2. duraklamali tur, tum-yesil headway
if want "$STEP" headway; then
  echo "== headway (duraklamali)   ~10-20 dk"
  for s in fixed_block_3aspect etcs_moving_block virtual_coupling; do
    python "$G/_sweep_headway.py" "$s" > "$R/headway-stopping-$s.txt"
  done
fi

# ----------------------------------------- 3. duraksiz tur, tum-yesil headway
if want "$STEP" express; then
  echo "== headway (duraksiz)      ~10-20 dk"
  for s in fixed_block_3aspect etcs_moving_block virtual_coupling; do
    python "$G/_sweep_express.py" "$s" > "$R/headway-express-$s.txt"
  done
fi

# --------------------------------------------------- 4. konvoy kurali, aralik
if want "$STEP" convoy; then
  echo "== konvoy taramasi         ~15-30 dk"
  python "$G/_sweep_convoy.py" --headway            > "$R/convoy-express.txt"
  python "$G/_sweep_convoy.py" --headway --stopping > "$R/convoy-stopping.txt"
fi

# ------------------------------------------- 5. konvoy kurali, kuplaj metrigi
if want "$STEP" convoylog; then
  echo "== kuplaj izleri"
  python run.py "$G/scenario-convoy.yaml" --headless \
      --log "$R/convoy-express.csv" --log-every 5 > "$R/convoy-express-run.txt"
  python run.py "$G/scenario-convoy-stopping.yaml" --headless \
      --log "$R/convoy-stopping.csv" --log-every 5 > "$R/convoy-stopping-run.txt"
  python presentation/charts/convoy_stats.py \
      "$R/convoy-express.csv" "$R/convoy-stopping.csv" \
      | tee "$R/convoy-metrics.txt"
fi

# ------------------------------------------------------- 6. bozucu etki
if want "$STEP" disruption; then
  echo "== bozucu etki             ~10 dk"
  for hw in 78 71; do
    for sys in etcs_moving_block virtual_coupling; do
      python run.py "$G/scenario-$hw-dwell.yaml" --propagation --system "$sys" \
          > "$R/dwell-$hw-$sys.txt"
      python run.py "$G/scenario-$hw-both.yaml"  --propagation --system "$sys" \
          > "$R/both-$hw-$sys.txt"
      python run.py "$G/scenario-$hw-tsr.yaml"   --headless    --system "$sys" \
          > "$R/tsr-$hw-$sys.txt"
    done
  done
fi

# ----------------------------------------------------------- 7. grafikler
if want "$STEP" figures; then
  echo "== grafikler"
  for c in network deckgfx results convoy2 disruption2 physics gradient; do
    python "presentation/charts/$c.py"
  done
  python _plot_motion.py presentation/figures/motion.png
fi

echo "bitti. ciktilar: $R   grafikler: presentation/figures"
