"""Midsurface testi icin ince cidarli ornek STEP parcalari uretir.

- thin_plate.step : 80 x 50 x 4 mm plaka  -> beklenen 1 orta yuzey (80x50, t=4)
- l_bracket.step  : iki ince plakadan L profil -> beklenen 2 orta yuzey

Kullanim: python make_thin_parts.py
"""

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.gp import gp_Pnt
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs


def write(shape, path: str) -> None:
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    writer.Write(path)
    print(f"Yazildi: {path}")


def thin_plate():
    return BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 80, 50, 4).Shape()


def l_bracket():
    t = 4.0
    base = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 80, 50, t).Shape()
    wall = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, t), t, 50, 40).Shape()
    return BRepAlgoAPI_Fuse(base, wall).Shape()


if __name__ == "__main__":
    write(thin_plate(), "thin_plate.step")
    write(l_bracket(), "l_bracket.step")
