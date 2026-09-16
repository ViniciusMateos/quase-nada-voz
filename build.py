"""Gera o executavel.

    python build.py         -> dist/QuaseNadaVoz.exe     (o app de verdade)
    python build.py --dev   -> dist/QuaseNadaVozDev.exe  (build de testes)

O Dev convive com o app normal: nome, icone, pasta de dados, trava de
instancia unica e registro de "iniciar com o Windows" separados. O canal
vai gravado dentro do .exe (channel.txt), lido por paths.py.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dev", action="store_true", help="gera o build de testes (Quase Nada Voz Dev)")
    args = parser.parse_args()

    channel = "dev" if args.dev else "prod"
    name = "QuaseNadaVozDev" if args.dev else "QuaseNadaVoz"
    icon = ROOT / "assets" / ("icon-dev.ico" if args.dev else "icon.ico")

    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "channel.txt"
        marker.write_text(channel, encoding="utf-8")
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name", name,
            "--onefile", "--windowed", "--noconfirm",
            "--icon", str(icon),
            "--add-data", f"{ROOT / 'assets'};assets",
            "--add-data", f"{marker};.",
            "--distpath", str(ROOT / "dist"),
            "--workpath", str(ROOT / "build" / name),
            "--specpath", str(ROOT / "build"),
            str(ROOT / "app.py"),
        ]
        subprocess.run(cmd, check=True, cwd=ROOT)

    print(f"\npronto: {ROOT / 'dist' / (name + '.exe')}  (canal: {channel})")


if __name__ == "__main__":
    main()
