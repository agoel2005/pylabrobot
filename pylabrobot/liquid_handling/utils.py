"""Utility functions for liquid handling operations."""

from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
from pylabrobot.resources.hamilton import STARLetDeck
from pylabrobot.resources import (
    TIP_CAR_480_A00,
    PLT_CAR_L5AC_A00,
    Trough_CAR_4R200_A00,
    Cor_96_wellplate_360ul_Fb,
    HTF,
    VWRReagentReservoirs25mL,
)

async def setup_liquid_handler():
    """Initialize the liquid handler with deck layout."""
    lh = LiquidHandler(backend=LiquidHandlerChatterboxBackend(), deck=STARLetDeck())
    await lh.setup()
    
    # Add resources to deck
    tip_car = TIP_CAR_480_A00(name="tip_carrier")
    tip_car[0] = HTF(name='tip_rack1')
    lh.deck.assign_child_resource(tip_car, rails=15)
    
    plt_car = PLT_CAR_L5AC_A00(name="plate_carrier")
    plt_car[0] = Cor_96_wellplate_360ul_Fb(name='plate1')
    lh.deck.assign_child_resource(plt_car, rails=8)
    
    # Add trough carrier with multiple troughs for different reagents
    trough_car = Trough_CAR_4R200_A00(name="trough_carrier")
    # TODO: abstract creating a trough for `trough_{MATERIAL_NAME}`
    trough_car[0] = trough_halide = VWRReagentReservoirs25mL(name="trough_halide")
    trough_car[1] = trough_boronic = VWRReagentReservoirs25mL(name="trough_boronic")
    trough_car[2] = trough_base = VWRReagentReservoirs25mL(name="trough_base")
    trough_car[3] = trough_catalyst = VWRReagentReservoirs25mL(name="trough_catalyst")
    # TODO: create easy way to using more than 4 troughs/number of materials exceeds one trough carrier
    # trough_car[4] = trough_solvent = VWRReagentReservoirs25mL(name="trough_solvent")
    
    lh.deck.assign_child_resource(trough_car, rails=2)
    
    return lh
