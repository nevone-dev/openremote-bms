#!/usr/bin/env python3
"""Run a named scenario and print the resulting building state.

Usage:  python run_scenario.py <scenario_name>
"""
import asyncio
import sys

from bms import BMSClient
from scenarios import apply_scenario, list_scenarios


async def main(scenario: str) -> None:
    print(f"Applying scenario: {scenario}")
    async with BMSClient() as bms:
        await apply_scenario(bms, scenario)
        building = await bms.get_building()
        print(f"\nBuilding state — {building.name}")
        for room in building.rooms:
            h, l, p = room.hvac, room.light, room.printer
            print(
                f"  {room.name:<14}"
                f"  temp={h.current_temp:.1f}°C"
                f"  hvac={h.mode:<8}"
                f"  lights={str(l.on):<5}"
                f"  toner={p.toner_level:.0f}%"
                f"  printer={p.status}"
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <scenario>")
        print(f"Available: {', '.join(list_scenarios())}")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
