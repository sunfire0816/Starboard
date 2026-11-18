# Starboard 12.8

A bigger update for salvagers, plus a fix for the screen reader.

## New: salvage, rebuilt

The SALVAGE tab now has six parts:

- **HOLD:** a salvage ledger for your ship. Pick your ship, then add each load of RMC, CM or scrap as you collect it. See how full you are, what the load is worth and your aUEC per hour. Click **SOLD IT** when you sell. The overlay can show your hold too (SETTINGS > OVERLAY > SALVAGE HOLD).
- **SPOTS:** scrapyards, wrecks, derelict outposts and the places salvage contracts send you. It marks which ones buy salvage and which contract sites are illegal.
- **CONTRACTS:** every salvage contract in the game from the Star Citizen Wiki, legal and illegal, with who gives it and what it is.
- **SELL:** sell a whole load. Type your RMC, CM and scrap (or click FROM HOLD) to see what each terminal pays for all of it, the best single stop, whether two stops pay more, and when a terminal can't take that much.
- **RUNS:** every salvage run you sold, with SCU, aUEC, time and aUEC per hour, plus totals for today, the last 7 days and all time.
- **SETUP:** salvage ships with their heads and stock modules, every scraper module compared (speed, beam size, how much material it keeps, price and where to buy), and module picks for your goal.

## Fixed

- **Screen reader error:** starting the screen reader for scan signatures showed "Method invocation failed because [System.Object[]] does not contain a method named 'op_Multiply'" and read nothing. It works again, with the reading improvements from 12.7.1.

## Install or update

1. Download **StarboardSetup-12.8.exe** below and run it. It updates your current Starboard in place, and your ships, ledger, plans and settings stay as they are.
2. If Windows says "Windows protected your PC", click **More info**, then **Run anyway**. Starboard is not code-signed, so Windows warns until enough people have run it.

Salvage gear and contract data comes from the Star Citizen Wiki (api.star-citizen.wiki) and prices from UEX. Starboard is a free fan project and is not affiliated with Roberts Space Industries or Cloud Imperium Games.
