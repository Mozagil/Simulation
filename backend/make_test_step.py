"""Test amacli ornek STEP dosyalari uretir (kutu + silindir birlesimi).

Kullanim: python make_test_step.py [cikti_yolu]
"""

import sys

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs


def build_shape():
    box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 40, 30, 20).Shape()
    axis = gp_Ax2(gp_Pnt(20, 15, 20), gp_Dir(0, 0, 1))
    cyl = BRepPrimAPI_MakeCylinder(axis, 8, 25).Shape()
    return BRepAlgoAPI_Fuse(box, cyl).Shape()


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "test_model.step"
    shape = build_shape()
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    writer.Write(out)
    print(f"Yazildi: {out}")


if __name__ == "__main__":
    main()
