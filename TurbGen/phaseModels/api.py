"""
TurbGen turbulence 'phase models' API.

Available phase models
----------------------
randPhase
  A uniform-distribution random-phase model.

"""
from main import Uniform

# This sets the default model (used in TurbGen.main)
default = Uniform()
