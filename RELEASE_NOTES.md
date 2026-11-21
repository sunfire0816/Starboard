# Starboard 12.8

A bigger update for salvagers, plus fixes for Pyro and the screen reader.

## New: salvage, rebuilt

The SALVAGE tab now has six parts:

- **HOLD:** a salvage ledger for your ship, or your mothership. It knows each salvage ship's buffer and cargo grid (Salvation 8 + 6 SCU, Vulture 16 + 12, Fortune 14 + 16, MOTH 240 + 224, Reclaimer 448 + 420), and works with any ship from MY SHIPS. Add RMC, CM and scrap as you collect it, plus the cargo boxes and components you pull off wrecks. See how full you are, what it's worth and your aUEC per hour. Sell it in parts at different terminals with **SOLD SOME**; the trip goes to RUNS when the hold is empty. The overlay can show your hold too.
- **SPOTS:** scrapyards, wrecks, derelict outposts and the places salvage contracts send you. It marks which ones buy salvage and which contract sites are illegal.
- **CONTRACTS:** every salvage contract in the game from the Star Citizen Wiki, legal and illegal, with who gives it and what it is.
- **SELL:** plan where to sell a whole load, cargo boxes included. It respects how much each terminal takes right now and gives you a list of stops, for the most aUEC or the fewest stops.
- **RUNS:** every salvage trip, with each stop, SCU, aUEC, time and aUEC per hour, plus totals for today, the last 7 days and all time.
- **SETUP:** salvage ships with their heads and stock modules, every scraper module compared (speed, beam size, how much material it keeps, price and where to buy), and module picks for your goal.

## Fixed

- **No position lock in Pyro:** after jumping to Pyro, Starboard kept saying you were in Stanton at the Pyro jump point. Its Pyro map was the old layout from before Alpha 4.1, when the game turned the whole system around the star. Pyro now matches the game (planets, moons, stations, Lagrange points and asteroid clusters), and DATA UPDATE keeps it that way. Starboard also remembers which system you were in between launches.
- **Screen reader error:** starting the screen reader for scan signatures showed "Method invocation failed because [System.Object[]] does not contain a method named 'op_Multiply'" and read nothing. It works again, with the reading improvements from 12.7.1.

## Install or update

1. Download **StarboardSetup-12.8.exe** below and run it. It updates your current Starboard in place, and your ships, ledger, plans and settings stay as they are.
2. If Windows says "Windows protected your PC", click **More info**, then **Run anyway**. Starboard is not code-signed, so Windows warns until enough people have run it.

Salvage gear and contract data comes from the Star Citizen Wiki (api.star-citizen.wiki) and prices from UEX. Starboard is a free fan project and is not affiliated with Roberts Space Industries or Cloud Imperium Games.
