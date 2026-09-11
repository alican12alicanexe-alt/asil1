# -*- coding: utf-8 -*-
"""Qt arayuzunu calistirilabilir bir dosyaya cevir.

    python build.py                 klasor halinde - hizli acilir, onerilen
    python build.py --onefile       tek dosya - tasinmasi kolay, acilisi yavas
    python build.py --windowed      konsol penceresini gizle

Paketledikten sonra:

    dist\\trainsim\\trainsim.exe --selfcheck

Senaryolarin pakete girdigini, kurulan hatlarin kalici bir yere yazilacagini ve
formun calistigini soyler. Once bunu kostur, sonra cift tikla.

Cikti dist/trainsim/ altinda. PyInstaller Windows'ta Windows'a, Linux'ta Linux'a
derler; capraz derleme yok, yani .exe icin bunu Windows'ta kosturman gerekiyor.

NEDEN KLASOR VARSAYILAN

"Sematigi izle" dugmesi programin kendisini --watch ile yeniden baslatiyor
(ui_qt.py: Window.watch). Tek dosya halinde her baslatma ~100 MB'lik paketi
gecici bir klasore yeniden aciyor: birkac saniye bekleme ve ikinci bir kopya.
Klasor halinde aninda aciliyor. Tek dosya yine de calisiyor, sadece yavas.

KURULAN HATLAR NEREYE GIDIYOR

Calistirilabilir dosyanin yanindaki scenarios/ klasorune (uicore.DATA). Paketin
icine degil: paket gecici bir klasore aciliyor ve cikista siliniyor, oraya
yazilan bir hat programla birlikte yok olurdu.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: Paketle birlikte gidecek veri: senaryolar olmadan program bos bir listeyle
#: aciliyor. Ayirac Windows'ta ; digerlerinde : - PyInstaller'in kendi kurali.
DATA_DIRS = ["scenarios"]

#: Kurulu olsalar da isimize yaramayanlar. Qt'nin kendi alt modullerine
#: dokunulmuyor: birini yanlislikla atmak calisma aninda patlar ve buradan
#: gorulmez.
EXCLUDE = ["matplotlib", "numpy", "pandas", "PIL", "scipy", "pytest",
           "IPython", "streamlit"]


def main(argv):
    onefile = "--onefile" in argv
    # Konsol varsayilan: --windowed ile derlenen bir program cokerse hicbir sey
    # soylemeden kapaniyor ve geriye bakilacak bir sey kalmiyor.
    console = "--windowed" not in argv

    separator = ";" if os.name == "nt" else ":"
    command = [sys.executable, "-m", "PyInstaller",
               "--name", "trainsim",
               "--noconfirm", "--clean",
               "--onefile" if onefile else "--onedir",
               "--console" if console else "--windowed",
               # Sematik gorunum kendi penceresini bir alt surecte aciyor ve
               # tkinter'i fonksiyon icinde ice aktariyor; adiyla soylemek
               # PyInstaller'in onu kacirma ihtimalini ortadan kaldiriyor.
               "--hidden-import", "trainsim.viz.schematic_tk"]
    for folder in DATA_DIRS:
        command += ["--add-data", "%s%s%s" % (os.path.join(HERE, folder),
                                              separator, folder)]
    for module in EXCLUDE:
        command += ["--exclude-module", module]
    command.append(os.path.join(HERE, "ui_qt.py"))

    print(" ".join(command))
    result = subprocess.call(command, cwd=HERE)
    if result != 0:
        print("\nDerleme basarisiz. PyInstaller kurulu mu?")
        print("    %s -m pip install pyinstaller" % sys.executable)
        return result

    built = os.path.join(HERE, "dist",
                         "trainsim.exe" if os.name == "nt" and onefile
                         else "trainsim" if onefile
                         else os.path.join("trainsim", "trainsim"))
    print("\nHazir: %s" % built)
    print("Kurdugun hatlar bunun yanindaki scenarios/ klasorune yazilacak.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
