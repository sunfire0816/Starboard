# Starboard

Your all-in-one companion for Star Citizen. One window for everything you do in the verse: where you are and how to get anywhere, mining and refining, hauling and trade routes, salvage, bounties and combat zones, where to buy any item or ship, your hangar, and every aUEC you earn and spend. No more jumping between websites.

Starboard was called SC Locator before version 8.6. The program files keep their old names (`sc_locator.py`, `run.bat`), so your saved data, shortcuts and settings carry over unchanged.

Covers Stanton, Pyro and Nyx (86 bodies, stars and jump points, about 515 locations).

## Download

Get the latest **StarboardSetup.exe** from the [Releases page](https://github.com/Sunfire0816/Starboard/releases/latest) and run it. No Python needed. Windows may say "Windows protected your PC" the first time: click **More info**, then **Run anyway** (see below).

Starboard checks this page once a day and tells you when a new version is out. Your settings, hangar, ledger and plans stay when you install the new version over the top.

Free and open source (GPL-3.0). Unofficial fan tool, not affiliated with Cloud Imperium Games (see Disclaimer).

## First start

The first time Starboard opens, a short **welcome guide** helps you connect the game log, enter your balance, add your ships and pick a text size and colors. You can open it again any time from SETTINGS.

## Setup (Windows, one time)

1. Install Python 3 from https://www.python.org/downloads/ (tick "Add python.exe to PATH" in the installer). No extra packages are needed.
2. Unzip this folder anywhere, for example `Documents\Starboard`.
3. Double-click `run.bat`.

## Starboard.exe and the installer

**Windows may warn you the first time.** Starboard.exe and the installer are not code-signed (a signing certificate costs money, and Starboard is free), so Windows SmartScreen can show "Windows protected your PC" until enough people have run it. Click **More info**, then **Run anyway**. Some antivirus programs also wrongly flag apps packaged with PyInstaller; if yours does, you can let it through or send the file to your antivirus maker as a false positive.

**If something goes wrong**, Starboard shows a plain message instead of crashing silently. COPY DETAILS copies what happened, so you can paste it in a message; the details are also saved in `crash.log` in your data folder.

**Your data** (settings, hangar, ledger, plans, game log history) is kept in `%LOCALAPPDATA%\Starboard` (paste that into File Explorer's address bar, or use OPEN MY DATA FOLDER under SETTINGS > ABOUT AND CREDITS). It is outside the program folder, so installing a new version, rebuilding Starboard.exe or uninstalling never touches it, and run.bat and Starboard.exe share the same data. The first time a new version starts, it brings over the old `user` folder from the program folder. To keep everything in the program folder instead (for a USB stick), put an empty file named `portable.txt` next to Starboard.

The `installer` folder has `build.bat`, which turns Starboard into `Starboard.exe` (no Python needed to run it) and, with Inno Setup 6 installed, into one `StarboardSetup-<version>.exe` to give to other players. The installer needs no admin prompt, adds a Start menu entry and a desktop shortcut, and installing a newer version over the top keeps your settings, hangar, ledger and plans. Steps are in `installer\README.txt`.

**SETTINGS > STARBOARD UPDATES**: Starboard checks once a day, when it starts, whether a newer release is out on [Starboard's GitHub page](https://github.com/Sunfire0816/Starboard/releases) (RELEASES FROM is already filled in) and offers to open the download page, showing the release notes. CHECK NOW checks right away. Starboard.exe also puts a shortcut on your desktop the first time it starts (DESKTOP SHORTCUT makes it again if you delete it).

## Using it

1. Leave Starboard open.
2. In Star Citizen, press **F9** (or open chat and type `/showlocation` yourself). Make sure the chat panel is visible (F12).
3. The game copies your coordinates to the clipboard. Starboard reads them within half a second and updates.

Run the game in borderless or windowed mode so the app and overlay can sit on top of it.

## Speed and arrival time

Take a second `/showlocation` while moving (anywhere from 1 second to 15 minutes after the first) and the app works out:

- **Speed** over the ground (or through space between planets), plus climb or descent rate.
- **ETA** to your target, based on how fast you are actually closing on it.
- **Turn hint**, such as "turn left 25°", comparing your direction of travel with the direction to the target. "On course" means within 5°.
- **Moving away** in amber if you are heading the wrong way.

Each new fix updates these, so the more often you fix, the more accurate they are. The F10 auto-repeat hotkey (below) does this for you.

## Scan signatures (SCAN tab)

When you ping in Star Citizen, every rock, gem deposit, harvestable and salvage piece shows a signature number. A group shows the single-item number times how many are in it. Starboard turns any number into what it is, before you fly over:

- **6340** = 2 Quantainium rocks (2 x 3,170)
- **11475** = 3 Laranite rocks (3 x 3,825)
- **12000** on a moon surface = most likely 3 ROC gem deposits, or 4 hand-mining gem deposits

Results are ranked using where you are: on a surface or in space, and what actually spawns on that planet or moon. Rare finds are colored (Legendary gold, Epic purple, Rare blue, Uncommon green). Anything not known to spawn where you are is shown in amber. The other possibilities are listed with a chance for each.

Ways to enter a signature:

- **In game, press F8**. A small box pops up; type the number and press Enter. The result appears on the overlay right away, so turn the overlay on.
- **SCAN tab**: type it in the box. Results update as you type.
- **Screen reader (beta)**: reads the number off your screen automatically. See below.

Other things on the SCAN tab:

- **MODE**: if you know what you are doing (for example, you are in a ROC), pick that mode and only matching results are shown.
- **TABLE**: a cheat sheet of every signature with its x2 to x6 group values.
- **TEACH**: for anything it does not know (a ship, a new rock after a patch, a mission object), type the number, click TEACH and name it. From then on that number, and groups of it, are recognized. Saved in `user\signatures_custom.json`.

Ships cannot be identified from their signature alone, because it changes with loadout and power, but you can TEACH the ones you see often.

### Screen reader (beta, Windows 10/11)

The screen reader watches one area of your screen and identifies any signature number that appears there, using the text recognition built into Windows (nothing to install).

1. In the SCAN tab click **SET AREA** and drag a box around where the signature number shows when you scan. Keep it fairly small: the area around your crosshair or the scan readout works best.
2. Click **START**. The status line shows what it reads, which helps you adjust the box.
3. Click **STOP** when you are done.

This is the one part of the app that could not be tested on a real Windows PC before release. If it shows an error or reads the wrong numbers, tell me what the status line says. Game HUD text can be hard for Windows to read, so F8 is the reliable fallback.

## Day and night

Under your position you will see whether it is day or night where you are, the local time on that planet (12:00 is when the sun is highest), the sun's height, and when the next sunset or sunrise happens, with the real-world clock time in brackets. The target panel shows the same for your target, so you know if you will arrive in the dark. Countdowns refresh every 30 seconds.

Times are worked out from the planet's spin and the star's position. Mountains and valleys are ignored, so the sun can disappear a few minutes early behind terrain.

## Getting to a target (quantum routes)

The target panel tells you how to get there:

- **The target has its own quantum marker** (outposts, landing zones and so on): quantum straight to it.
- **No marker** (most caves, bunkers, your saved spots and logged finds): quantum to the best **orbital marker** (OM-1 to OM-6) of that planet or moon, then the heading and ground distance to fly after you drop out.
- **Already on the same planet**: whether to fly direct or jump to an OM first, whichever is quicker.

OM-1 and OM-2 sit over the north and south poles. OM-3 to OM-6 sit over the equator.

## Map

The **MAP** tab shows a flat map of the planet or moon you are on (or any other, from the list):

- you (white), every location (bright cyan has a quantum marker), your saved spots (orange) and logged finds (green diamonds)
- the six orbital markers
- a dashed green path to your target, starting from you or from the OM you should jump to
- the night side shaded darker, updated every 30 seconds

Hover a dot to see its name and distance from you. Click it to make it your target.

## Mining log

Found something worth coming back for? Run `/showlocation` at the deposit, then click **LOG FIND**. Pick the material, the method (ship, ROC or hand), and optionally the quality from your scanner, an amount and a note.

Logged finds:

- are listed in the **LOG** tab, closest first, filterable by material
- show as green diamonds on the map and in Nearby
- appear at the top of **FINDER** for that material ("Your log, 3 finds")
- can be set as a target, like any other location (double-click)

To remove one, select it in the LOG tab and click DELETE, or right-click it in Starmap. The log is stored in `user\mining_log.json`.

## Keeping the map current (SETTINGS > MAP DATA)

After a patch, click **CHECK FOR UPDATES** in the **DATA** tab. The app downloads the latest coordinates and tells you what changed (new, moved or removed locations, rotation changes). Downloads come from:

- **VerseTime** on GitHub: Stanton and Pyro planets, moons and locations
- **StarMap**: Nyx, orbital marker heights, and any Nyx locations StarMap has (such as Levski, once it lists it). Untick **INCLUDE NYX (STARMAP)** to skip it. If StarMap is down, your current Nyx data is kept.

Good to know:

- Your saved spots, mining log and calibrations are never touched.
- The old data is backed up first (the last 3 updates are kept). **UNDO LAST UPDATE** puts it back.
- If the update changes the rotation data of a planet you calibrated, the app offers to reset that calibration, since the new data usually makes it unnecessary.
- Ore lists are not part of the update.
- Nothing is changed if a download fails or looks wrong.

## Sharing spots with friends

Also in the **DATA** tab. Pick what to share (saved spots, logged finds, or both, and optionally one system), then:

- **EXPORT FILE**: saves a `.json` file (or `.csv` for a spreadsheet) to send to a friend.
- **IMPORT FILE**: loads a friend's file, or a community list.
- **COPY CODES**: copies short text codes, one per spot, ready to paste into Discord. Each looks like `SCLOC1|poi|Daymar|82.008|-278.683|43.649|Cave|Secret cave||`. Discord fits about 25 per message.
- **PASTE CODES**: your friend copies your Discord message and clicks this.

You can also right-click a single spot or find in Starmap (or use **COPY CODE** in the LOG tab) to copy just that one.

Imports show what was found and ask before adding anything. Spots you already have are skipped. Imported entries are labeled with where they came from (for example "[from Irish]").

Community lists in CSV need a name column, a planet or moon column (`body`, `planet` or `moon`), and either `x`, `y`, `z` in km (relative to the planet center, like StarMap's location data) or `lat` and `lon` in the same convention this app shows. An optional `alt_km` or `height` (meters) column sets the height.

## In-game overlay

Click **OVERLAY ON** for a small see-through panel that floats over the game:

- With a target: distance, ETA, turn hint and an arrow. Once you are moving, the arrow is relative to your direction of travel ("REL"): straight up means fly straight ahead. Before that it points by compass ("N↑").
- With a target on another planet or moon: which OM to quantum to, then the heading and distance.
- Without a target: your planet or moon, lat, lon, altitude and the closest location.
- Along the bottom: your speed and the day or night time (at the target if you have one).

The overlay starts **locked**, so mouse clicks go straight through it to the game. Click **UNLOCK** to drag it where you want it (it turns amber), then **LOCK** again. The position is remembered.

## Home screen (HOME tab)

Starboard opens on HOME. The **RIGHT NOW** card at the top suggests what to do: refinery jobs ready to collect, the best trade from where you are, contracts you have running, or the best paying missions in your system. Each card is one thing you can do in the game (Navigate, Mine, Haul, Explore, Shop, Money, Hangar, Combat, Salvage), shows where you stand right now, and has buttons straight to the right tab. The tabs along the top follow the same activities: NAVIGATE (Nearby, Map, Space, Starmap), MINE (Scan, Ores, Finder, Log, Refining, Loadout), SALVAGE (Hold, Spots, Contracts, Sell, Runs, Setup), COMBAT (Bounties, Zones), HAUL, SHOP, MONEY, HANGAR, MISSIONS and SETTINGS (Settings, Data), with LIVE right after HOME.

The look follows the RSI website: deep navy panels, sky-blue highlights, orange buttons for the main action on each screen, and a coloured bar on each HOME card so you can find a section at a glance.

**COMPACT** (top right) folds the big position panel into one line, so every tab gets more room; **FULL** brings it back. The app remembers your choice. Rest the mouse on a card title for a short description.

**SEARCH** at the top finds anything in one box: a place, a planet or moon, a ship, an item, fuel, cargo or an ore. Type part of a name and double-click a result (or press Enter): places become your target, planets open in NEARBY, cargo opens trade routes, ores open the ore finder, and items and ships show every shop that sells them. Esc clears the search.

## Refinery jobs (MINE > REFINING)

When you drop ore at a refinery, click **NEW JOB** and enter the refinery (the closest one is filled in when you are there), the ores and SCU, the method and the time the terminal shows (`2h 15m` or `2:15`). The dialog shows the yield bonus for each ore at that refinery and where the best bonus is. The cost can go straight into your ledger.

The list counts down to each job. When one is ready, you get a message in the app and the overlay, and the MINE card on HOME says so. **FLY TO REFINERY** takes you back; mark the job **COLLECTED** when you pick it up.

## Salvage (SALVAGE tab)

**HOLD** is your salvage ledger. Pick your ship: it fills in the salvage buffer (what the ship holds inside before you box it out) and the cargo grid, so a Salvation shows 8 + 6 SCU and a Reclaimer 448 + 420. Any ship from MY SHIPS works too, so if you live on a mothership, pick it and add whatever your other ships bring back.

- **Salvage:** type the SCU you collected and click **RMC**, **CM** or **SCRAP**. **SET EXACT** sets each one to what your ship shows.
- **From a wreck:** add cargo boxes you pulled off (pick the commodity) and ship components (name, how many, and what each is worth if you know).
- **The card** shows how full you are, what everything is worth at today's best prices, how long the trip has run and aUEC per hour. Breaks longer than 30 minutes don't count, so a trip over several days still shows a fair rate. The overlay can show it too (SETTINGS > OVERLAY > SALVAGE HOLD).
- **Selling:** you rarely sell a big load in one place. **SOLD SOME** takes what you sold at one terminal out of the hold and keeps the sale; **SOLD ALL** sells what's left. When the hold is empty the whole trip, every stop included, goes to RUNS and your ledger.

**SPOTS** lists scrapyards, wrecks, derelict outposts and the places salvage contracts send you, closest first. It marks the ones that buy salvage and the illegal contract sites. Double-click to fly there.

**CONTRACTS** lists every salvage contract in the game from the Star Citizen Wiki, legal and illegal, with who gives it and what it is.

**SELL** plans where to sell the whole load: RMC, CM and scrap, or **FROM HOLD** to include your cargo boxes. Each terminal shows what it pays for what it takes right now. The plan card shows the one stop that takes it all if there is one, otherwise a list of stops: **Most aUEC** sends each material to the best price first, **Fewest stops** uses as few terminals as it can. Anything nobody nearby buys is listed. **LOG SALE** after you sell at the selected terminal.

**RUNS** keeps every salvage trip: what you sold, where, what it paid, how long it took and aUEC per hour, with totals for today, the last 7 days and all time.

**SETUP** shows each salvage ship's heads and stock modules, compares every scraper module (speed, beam size, how much material it keeps, price and where to buy) and suggests modules for your goal: the most material per hull, big hulls quickly, or a balance.

## Settings (SETTINGS tab)

Make Starboard easier to see and read:

- **Text size**: Small, Normal, Large, Extra large or Huge. The window grows with the text.
- **Font**: the default HUD font, or an easier-to-read one such as Verdana. Atkinson Hyperlegible and OpenDyslexic are free fonts made for low vision and dyslexia; install one in Windows and it appears in the list.
- **Color mode**: Default, Red-green colorblind (protanopia and deuteranopia), Blue-yellow colorblind (tritanopia) or High contrast. The swatches show what good, warning and danger look like, and help text names the right colors in each mode (for example "blue is best" instead of "green").
- **Window**: a fixed size or remember the last size and position, window opacity (handy over the game), overlay opacity (how see-through the in-game overlay is), always on top, and start in compact view.
- **Comfort**: turn off the blinking status light, and turn hover help tips on or off.
- **Typing in pickers**: every box you can type a ship, place, refinery or ore into shows the matches in a list under it as you type. Up and Down move through it, Enter or a click picks one, Escape closes it. Search boxes filter as you type.
- **EVENTS**: a month calendar of major Star Citizen events for this month and the next three (the arrows step through them): IAE, Luminalia, the Daymar Rally, the Red Festival, Coramor and other big events, with Free Fly marked. Solid bars are confirmed by RSI; outlined bars are yearly events whose dates are not announced yet, placed at their usual time. Click a bar or OPEN for details. The list is `data/events.json` and is updated with new versions.
- **Tickers**: two strips under the banner. MARKET scrolls every commodity's average price at terminals (UEX, per SCU) with how much it moved since about a day ago, green for up and red for down, biggest moves first. Starboard keeps a small price history each time prices update; until it has a day of history the change is against UEX's usual price. NEWS scrolls, newest first: whether the game servers are online, patch deployments and incidents (RSI's status page, status.robertsspaceindustries.com), new videos from RSI's Star Citizen YouTube channel, and Comm-Link posts (through the Star Citizen Wiki API, which can run a week or two behind). Checked every 10 minutes; turn on the servers alert under ALERTS to hear when the servers go down or come back. Hover to pause a strip; click a commodity for its trade routes or a post to read it. Turn either one off here.
- **Overlay**: pick what the in-game overlay shows: position and target, your hauling run, signature scans, refinery timers (time left on your next jobs), current contracts from the game log, and this session's earnings (money made and per hour). Each part only appears when it has something to show, and the overlay grows to fit: the hauling run hides once the run is finished (after two minutes) or when you have not touched it for four hours, and contracts hide when you have none active.
- **Alerts**: a pop-up in the bottom right corner of your screen and a sound when a refinery job is ready, when a contract completes or fails, when you enter a new jurisdiction carrying illegal cargo you bought, and when the game servers go down or come back (Altruciatoxin, E'tam, Freeze, Maze, Neon, SLAM, WiDoW and similar). Turn each one, the pop-up and the sound on or off; TEST ALERT shows one. Click a pop-up to close it.
- **Clock**: 24 hour (15:45) or 12 hour (3:45 PM). Every time Starboard shows (the last position fix, the activity feed, the ledger, refinery jobs) uses your PC's clock and time zone.

Opacity, overlay opacity, on top, compact view, clock, blinking and tips change right away. Text size, font, color mode and window size apply when you press **APPLY AND RESTART**. Your data is kept; set your target again after the restart. With large text on a 1080p screen, COMPACT view gives the tabs the most room.

## Live game log (LIVE tab)

Star Citizen writes what happens in your session to a file called `Game.log` in its install folder (for example `C:\Program Files\Roberts Space Industries\StarCitizen\LIVE`). Starboard finds it by itself and follows it while you play. It only reads the file; it never touches the game.

What it does with it, each switch under **AUTOMATIC**:

- **TRADES**: every commodity you buy or sell at a terminal goes into your ledger with the exact amount the game charged or paid. While this is on, a hauling run no longer adds its own estimates for the same trades.
- **SHOP BUYS**: items you buy in shops go into the ledger (magazines and ammo as Ammunition). If the game then says the purchase failed, the entry is taken out again.
- **CONTRACT PAYOUTS**: when a contract completes, its reward goes into the ledger. The game log does not say how much you were paid, so Starboard looks the contract up in the Star Citizen Wiki; these entries are marked with ≈, so check them against your mobiGlas.
- **BOUNTIES**: bounty contracts you accept appear in COMBAT > BOUNTIES with their risk rank, and are marked done or failed by themselves.
- **MY SHIP**: when you fly or plot a route in a ship that is in MY SHIPS, it becomes your active ship, so hauling uses its hold.

The tab also shows your pilot name, where you are (landing zone, station or outpost), the ship you last flew and whether you are in an armistice zone, plus a list of this session's contracts and an activity feed: locations, contracts, trades, purchases, blueprints, ships you destroy and times you go down. With COMPACT on, the one-line bar shows the game's location and ARMISTICE even before your first F9.

Click a contract in the list for its details from the Wiki (type, giver, reward and where it sends you); **FLY TO** sets that place as your target and **WIKI** opens its page. **SESSIONS** (here and in MONEY) shows each play session: how long, what you earned and spent, profit per hour and what paid the most. The status line shows this session's profit as you play.

Starboard never imports old sessions: the first time it runs it starts from that moment. After that, if you close Starboard during a session and open it again, it catches up on what happened in between without adding anything twice. If the log is not found, click **CHOOSE FILE** and pick `Game.log` yourself.

## Asteroid belts (MINE > BELTS)

How to get into belts that are not on the quantum list, and whether you are in one.

- **Aaron Halo** (Stanton): pick a route and Starboard tells you where to quantum and the distance left at which to drop out, to land in band 5, the densest band. Press F9 in game and the routes start from exactly where you are; without a fix it lists routes from the main stops. The page lists all ten bands and their thickness.
- **Yela's ring** (Stanton): quantum to Yela, then fly out to 482 to 782 km from its centre.
- **Glaciem Ring** and **Keeger Belt** (Nyx): quantum straight to Delamar (Glaciem) or a QV Breaker station (Keeger), or drop out on a route that crosses them.
- **Akiro Cluster** (Pyro): on the quantum list; jump straight there.
- **WHERE YOU ARE**: after each F9, Starboard says whether you are in the belt, which band, or how far you still have to go (and whether to fly up or down into it).
- **SHOW ON OVERLAY** puts the route on the in-game overlay (the "Belt route" part under SETTINGS > OVERLAY): where to quantum, the number to drop out at, and after F9 whether you made it.

Starboard cannot see your quantum travel while it happens, so watch the distance left yourself. Quantum travel can steer around planets and moons, so the number can be off a little: press F9 after you drop out. Checked against the Star Citizen Wiki's routes: Hurston to ArcCorp drops out at about 10 Gm left, and Crusader to CRU-L2 at about 745,000 km, both matching the Wiki.

Sources: Aaron Halo bands from Cornerstone's Aaron Halo survey (cstone.space); Yela's ring and the Akiro Cluster from game data through the Star Citizen Wiki; the Nyx belts from where Delamar and the QV Breaker stations sit.

## Mining loadout (MINE > LOADOUT)

Plan the lasers, modules and gadget for your mining ship before you buy them. Pick the ship (Prospector, MOLE with its three heads, Golem, ROC or any size 1 or 2 laser), then a laser for each head and a module for each of its slots. The table shows what you end up with: mining power, extraction power, range, and every effect (resistance, instability, optimal window, charge rates, inert materials, shatter damage and more), in green when it helps you and amber when it hurts. Effects stack by multiplying, the way the game does. Gadgets go on the rock, so they count for every laser. Untick **COUNT ACTIVE MODULES** to see your numbers without active modules such as Stampede running. The line under the table gives the total cost and the cheapest place for each part (UEX prices). Your setup is remembered for each ship.

**Can I break this rock?** Type the rock's mass, resistance and instability from your mining scanner into the ROCK boxes. Starboard says yes or no, how much of your laser power you need (adding all your lasers together), and if it is a no, which gadget would make it breakable. It uses the formula most community mining tools use, so treat it as a good estimate rather than a promise.

Stats come from the Star Citizen Wiki API, downloaded the first time you open the tab and refreshed every two weeks (or with **UPDATE**).

## Missions (MISSIONS tab)

Every mission in the game, from the Star Citizen Wiki API: name, type, who gives it, systems, reward and rank. Search by name, and filter by type, system and legal or illegal. Illegal missions are red; missions that give a blueprint are purple. Click one to see its details (time, players, shareable, reputation, the standing it needs, where it is offered, blueprints and the briefing); double-click opens its Wiki page. The list downloads the first time you open the tab and refreshes every few days.

## Your own data (SETTINGS > MY DATA)

Starboard builds its own database from your game (`user\starboard.db`), so it relies less on outside sources and keeps working when they are down:

- **Commodity prices** you actually bought and sold at, per place, next to UEX's current price there (green when you did better, amber when worse).
- **Shop purchases**: what you paid for items and where. These also show in SHOP as purple **YOU PAID** rows.
- **Places visited**: every landing zone, station and outpost the game says you were at, and how often.
- **Contracts**: every contract you took, where you took it and how it ended, plus what it really paid.

Contract rewards are the gap in outside data: the Wiki often has none and the game log does not say. When a contract pays, click it on the LIVE tab and press **I WAS PAID** (or correct the payout in MONEY). Starboard remembers it, uses it the next time you finish that contract, and shows it in MISSIONS marked "(you)".

**IMPORT OLD GAME LOGS** reads the `logbackups` folder next to Game.log once, so your database starts with your past sessions too. Nothing in it leaves your PC.

## The game's own text (SETTINGS > MY DATA > GAME TEXT)

Star Citizen ships with a text file that holds the real names of every item, ship and place, plus contract titles and briefings. Starboard reads it so the game log shows "Parallax Rifle Battery (80 Cap)" instead of `volt_rifle_energy_01_mag`, LIVE shows a contract's briefing, and MINE > ORES adds what the game says can be mined on each planet and moon.

Nothing extra is needed. Starboard looks in your `StarCitizen\LIVE` folder (next to Game.log):

1. If a text mod such as StarStrings is installed (`LIVE\Data\Localization\english\global.ini`), it uses that, with the mod's extra details.
2. Otherwise it reads the standard text straight out of the game's `Data.p4k`, read-only. The game files are never changed.

The parts it needs are saved in `user\gametext.json` and only read again after a game patch. If Starboard cannot find it, press **PICK FILE** and choose `global.ini` or `Data.p4k`. The text belongs to the game and stays on your PC.

## Finding your way around

- The panel at the top stays a slim one-line strip until Starboard has your position (press F9 in game), so the tabs have room. It shows where the game log says you are and what to do next. Press COMPACT to keep it slim even with a position.
- The badge at the top right says WAITING FOR GAME, IN GAME, or POSITION LOCKED.
- Empty tables tell you what to do to fill them.
- HOME shows the latest things the game log saw (trades, contracts, where you are), with OPEN LIVE for the full feed.
- Rest the mouse on a button to see what it does (turn this off in SETTINGS).

## Ship builder (HANGAR > SHIP BUILDER)

Plan a loadout like a DPS calculator, then see where to get every part.

- **Pick a ship** (it starts with the ship you marked FLYING THIS). Its slots are listed by group: weapons (inside gimbals and turrets too), missiles, shields, power, cooling and quantum.
- **Click a slot** to see every part that fits it, best first, with its key stat, cheapest price and how to get it (Buy, Craft, Loot). Double-click a part, or press FIT THIS PART, to fit it. Changed slots turn orange; STOCK PART or STOCK puts them back.
- **Totals** at the top update as you go: DPS, alpha, missiles, shield HP and regen, power use against what your power plants make, cooling, quantum speed, and what the changes cost. Each shows the difference from the stock ship. They assume everything is switched on, so use them to compare builds.
- **Class and signature**: every part shows its class (Military, Stealth, Civilian, Industrial, Competition) and grade (A best, D most basic), and the EM and IR signature it gives off while switched on. Stealth parts are purple, and CLASS above the parts list shows only one class. Lower EM and IR make you harder to spot and lock onto: a stealth cooler gives off about a third of a military one. The PARTS EM / IR total shows what your build adds, against stock. Each part's page also shows its health and how much distortion it takes before it shuts down, with a line on what its class means.
- **Every part** shows its stats, the shops that sell it (cheapest first; click one to set it as your target) and its blueprint, which opens in CRAFT with the contracts that give it and the materials it needs.
- **Missiles**: click a missile slot and press CHANGE RACK to see the racks that fit that hardpoint. A different rack can carry more or bigger missiles; the missile count, damage and cost update with it.
- **COMPARE** puts this build next to the one picked in My builds (or the stock ship): every total, side by side, with the difference.
- **PUT ON MY SHIP** makes this the loadout of that ship in MY SHIPS (it shows in the LOADOUT column). Picking that ship in the builder opens its loadout, and LOADOUT in MY SHIPS jumps straight to it.
- **SHARE CODE** copies a short code (it starts with SB1:) to paste in Discord; **LOAD CODE** opens one.
- **SHOPPING LIST** lists every part you changed with the cheapest place to buy it, or the blueprint to craft it, and the total cost. **SAVE BUILD** keeps a build; pick it again from My builds. To remove one, pick it in My builds and press **DELETE**.

Data: Star Citizen Wiki (ships, slots and parts) and UEX (prices). Parts update weekly by themselves.

## Crafting (CRAFT tab)

Every blueprint in the game, linked to everything it takes to make it. Pick a blueprint on the left (or type in FIND) and the page on the right walks you through it:

1. **Get the blueprint:** the contracts that can give it, each with its faction, LEGAL or ILLEGAL, the reputation you need, the system and the drop chance, plus the easiest way to get it.
2. **Gather the materials:** how much of each, and where it is mined (nearest or best spot).
3. **Refine the ore:** the refinery with the best yield for each material.
4. **Craft it:** how long it takes, and what dismantling gives back.

Every blue underlined name is a link, and BACK goes to the page before:
- **A material** shows where it spawns (each place opens MINE > ORES), the refineries by yield, terminals that sell it, and every blueprint that uses it.
- **A contract** shows its faction, legality, the reputation it needs and gives, the blueprints it can give, the contracts you must do first, where it is (click to set a target) and its briefing. SHOW IN MISSIONS jumps to it in the MISSIONS tab.
- **A faction** lists its contracts that give blueprints (lowest reputation first) and every blueprint you can get from it.

**MY PLAN** (crafting plan): on any blueprint page press **+ Add to my crafting plan**, as many blueprints and as many of each as you like. The plan then shows, all in one place:
- what you want to make (change the amounts with - and +), and whether you already have each blueprint;
- the blueprints you still need, with the easiest contract for each;
- every material they need together, how much you already have (click HAVE to type it), what is still missing, and for each missing one where to mine it, the best refinery and the cheapest place to buy it instead;
- what is left to do before you can craft.

The plan and your HAVE amounts are kept in `user\craft_plan.json`.

**FIND MY BLUEPRINTS** reads your game logs for every "Received Blueprint" message, so the list marks the ones you own (green). New ones are added by themselves while you play. Filter with SHOW: not owned yet, I own, from contracts. The MISSIONS tab has a BLUEPRINTS button, and HOME search finds blueprints too. Data: api.star-citizen.wiki, updated daily.

## Automatic updates (SETTINGS)

Starboard keeps outside data current by itself: prices (every 3 hours by default), missions and blueprints (daily), ship parts, mining gear and the map (weekly). Change how often, or turn it off, under **AUTOMATIC UPDATES**; **UPDATE ALL NOW** fetches everything at once. Each line shows when that data was last updated. Everything downloaded is kept, so Starboard still works offline.

## Combat (COMBAT tab)

**BOUNTIES** keeps track of the bounty contracts you accept: the target, its risk rank (VLRT to ERT), the reward and where it is (pick a place to be able to fly there, or type a note such as "near Yela OM-3"). Mark a bounty **DONE** when you collect and the reward goes into your ledger (untick **ADD PAYOUTS TO MY LEDGER** to stop that), or **FAILED** if it went wrong. The line under the list shows today's and all-time bounties, earnings and the average per bounty.

**ZONES** lists places by who holds them, closest first: security (green), outlaw stations such as GrimHEX, Ruin Station and Checkmate (red), outlaw hideouts such as forward operating bases and derelict settlements (amber), and bunkers and facilities used by mercenary and bounty missions. Pyro and Nyx have no UEE law, which the tab points out when you are there.

## Shop finder (SHOP tab)

Where to buy anything, with prices from UEX (downloaded with the trade data; click UPDATE PRICES in HAUL for fresh ones).

- Type what you want (a weapon, armor, a mining head, a ship) or pick a **CATEGORY**: Ships to buy, Ships to rent, Fuel, Refinery yields, or any item group. **SYSTEM** limits it to the system you are in (Current), one system, or All.
- Double-click a result to see every shop that has it: the shop, where it is, the price, how far it is from you (closest first once you have a fix) and how old the price is. The best price is green; prices older than a week are grey.
- Double-click a shop (or **FLY TO SHOP**) to make it your target. For ships, **ADD TO HANGAR** adds the ship to My Hangar.
- **Refinery yields** shows, for each ore, which refinery gives the biggest bonus (or smallest penalty), plus the refining methods with the best yield.

## My Hangar (HANGAR tab)

Add the ships you own once with **ADD SHIP**: pick the ship (type to search), its setup if it has modules (such as the Galaxy with or without the Cargo Module), and an optional nickname. You see each ship's maker, roles, crew and cargo size.

- **FLYING THIS** (or double-click) marks the ship you are in. Hauling then uses its cargo hold automatically.
- **PARKED HERE** saves where you left the selected ship: press F9 at the pad or hangar first.
- **FIND MY SHIP** makes its parking spot your target, so the compass and overlay lead you back.

## Hauling (HAUL tab)

At the top, pick your **SHIP** (type part of the name to search). Ships with modules are listed once per setup, for example **RSI Galaxy + Cargo Module** (720 SCU) and **RSI Galaxy (no cargo module)** (64 SCU), or the Retaliator with its bow and stern cargo modules. The cargo size (**SCU**) fills in automatically. If you type a different SCU, it is remembered for that setup. **BUDGET** is optional and limits how much you spend on cargo (`250k` and `1.5m` work). These are remembered.

Prices, terminals and ships come from **UEX Corp** (community-reported, refreshed hourly). The first time you open the tab it downloads them (about 10 seconds). Click **UPDATE PRICES** before a session for fresh numbers; the line under the ship row says how old they are.

**ROUTES**: the best buy-here, sell-there runs for your hold, biggest profit first. Filter by system and commodity. **START** picks where you buy: **WHERE I AM** shows only what the terminals at your last fix (within 25 km) sell and where to take it, so press F9 at a TDD and pick it. The distance options keep routes that start within 1, 5 or 20 Gm of you. Terminals are shown by their in-game names, such as TDD Area 18 or ARC-L2. Click a row for the full details: prices per SCU, cost, profit, and whether stock, demand or your budget limited the amount. Grey rows have prices older than a week, so check them in game. Double-click a row to start it as a run.

**CONTRACTS**: enter the hauling contracts you accepted. Each one has a title, reward and one or more legs (pick up at, deliver to, cargo, SCU). **PLAN RUN** puts every pickup and drop-off of the active contracts in the shortest order that never goes over your hold and never delivers cargo you have not picked up yet. It starts from your current position. A leg bigger than your hold is split into several trips automatically. Use **ON / OFF** to leave a contract out of the plan without deleting it.

**PLAN TRIP** makes one trip out of everything you have going: the active contracts (in the same safe order as PLAN RUN), a stop at each refinery where a job is ready or will be within the hour (put where it adds the least flying), and the best trade that fits on the way with the cargo space the contracts leave free (buy at one stop, sell at a later one). The trip then runs in the RUN tab like any other run, with the expected money logged as you go.

**RUN**: your stops in order, what to load or unload at each, and how much is on board after. The current stop is always your target, so the compass, quantum route and overlay guide you there. Press F9 at the stop and it is marked **HERE**; once you leave, it moves on to the next stop by itself (turn off **AUTO NEXT WHEN I LEAVE** to do it by hand with **NEXT STOP**). Double-click a stop to jump to it. The run is saved, so it survives closing the app. With the overlay on, a strip along the bottom shows the stop number, the place and what to do there.

## Ledger (LEDGER tab)

Keeps track of your money: every purchase and every payout, with a running balance.

- **First time:** click **SET BALANCE** and type what your in-game wallet shows. Do it again any time; if the numbers differ, a correction is added so the balance matches the game again.
- **Adding an entry:** pick **Expense** or **Income**, a category (fuel, repairs, trade purchase, contract payout, bounty and so on, or type your own), the amount and an optional note, then press Enter or **ADD**. Amounts like `12500`, `12.5k` and `1.2m` all work, and a minus sign always means spending. Where you were (from your last F9) is saved with it.
- **Hauling runs fill it in for you** (turn off **LOG HAULING RUNS AUTOMATICALLY** if you prefer): leaving a buy stop logs the purchase, leaving the sell stop logs the sale, and the last drop-off of a contract logs its reward and marks the contract DONE. These use the expected prices, so they show **≈** until you double-click and enter the real amount.
- The period box (Today, 7 days, 30 days, All time) sets what the table and the IN, OUT and NET totals cover. Below the table you see where most money came from and went.
- **EDIT** (or double-click) and **DELETE** fix mistakes. **EXPORT FOR EXCEL** saves everything for Excel or Google Sheets.

## Finding caves, outposts and other places (NEARBY tab)

NEARBY lists every known location on the planet or moon you are on, closest first, with the distance over the surface and the compass bearing. Pick a **TYPE** (Cave, Outpost, Underground bunker and so on) to see only those, or type part of a name in **SEARCH**. Double-click any row to make it your target, then follow the compass and overlay.

Use **BODY** to look at another planet or moon, for example to list every cave on Lyria while you are still at ArcCorp. Distances are then straight-line from you, and the TARGET box tells you which orbital marker to quantum to.

The game's public location data has very few caves. **SETTINGS > MAP DATA > CHECK FOR UPDATES** with **ALSO GET NYX AND CAVES** ticked also downloads the caves and surface places from the Star Citizen Location Finder (about 800 caves across Stanton and Pyro, plus Onyx Facilities, security posts and more), and StarMap's points of interest when that service is up. A body's new places are only added if the source and the existing data agree on the places both list, so wrong positions are kept out. Some moons, such as Lyria and Yela, have no caves in any source yet; caves you find yourself can be saved with SAVE SPOT.

## Ore finder

The **FINDER** tab: pick a material (Quantainium, Riccite, Savrilium, Hadanite and so on) and it lists every planet, moon or Nyx belt where it spawns, best share first. Ties go to the closest. The nearest source in your current system is marked with ◆ in green, and "here" means you are already on it. Double-click a row to open that body's full ore list.

## Tabs

Click any column heading to sort by it; click again to reverse. The arrow shows the current order, and it stays sorted when the list refreshes.

The tabs run left to right in four groups: getting around, the things you do, your gear and money, and info. Hover over a tab to see its hotkey.

| Tab | Inside | What it shows |
| --- | --- | --- |
| HOME | | Activity cards (in the same order as the tabs), RIGHT NOW suggestions and one search box for everything. |
| LIVE | | What the game's own log says: trades, purchases, contracts, location, ship and armistice, added to your ledger by itself. |
| NAVIGATE | NEARBY, MAP, SPACE, STARMAP | Places near you (filter by type, double-click to target), a flat map with you, your target and the night side, the nearest planets, stations and jump points, and every location in every system. |
| MINE | SCAN, FINDER, BELTS, ORES, LOG, REFINING, LOADOUT | In the order of a mining trip: identify a scanned rock, where to find a material, how to get into an asteroid belt, what ores a body has, your mining log, refinery jobs, and your mining loadout. |
| SALVAGE | HOLD, SPOTS, CONTRACTS, SELL, RUNS, SETUP | Track what is in your hold, find wrecks and contracts, sell the whole load for the most, and plan your salvage gear. |
| HAUL | ROUTES, CONTRACTS, RUN | Trade routes, hauling contracts and the live run tracker. |
| COMBAT | BOUNTIES, ZONES | Bounty contracts and payouts, and where security, outlaws and hostile facilities are. |
| MISSIONS | | Every mission with its reward, giver, requirements and the blueprints it gives. |
| SHOP | | Where to buy any item, buy or rent a ship, refuel, and refine for the best yield. |
| CRAFT | | Blueprints, the materials they need, and your crafting plan. |
| HANGAR | MY SHIPS, SHIP BUILDER | The ships you own and where they are parked, and the full loadout builder. |
| MONEY | | Your ledger: purchases, payouts and balance. |
| EVENTS | | Major events this month and the next three. |
| SETTINGS | GENERAL, MAP DATA, MY DATA | Look and feel, overlay, alerts, hotkeys and updates; game data updates and backups; what Starboard has learned from your game. |

Click any column heading to sort by it; click again to reverse. The arrow shows the current order, and it stays sorted when the list refreshes.

## Save your own spots

Found a cave, a good deposit or a wreck? Stand on it, run `/showlocation`, then click **SAVE SPOT**. Saved spots show in orange, stay fixed to the planet surface, and appear in Nearby and Starmap. They are stored in `user\custom_pois.json`.

## If positions look shifted (Calibrate)

Planets rotate, and the game's rotation offset can change after a patch. If the closest outpost is clearly wrong when you are standing right at it, land at any known outpost, run `/showlocation`, click **CALIBRATE** and pick the spot you are at. That body stays corrected until you reset it.

## System selector

All three systems use the same coordinate origin, so the app decides which system you are in by checking what you are near (a planet or moon first, then stations, jump points and Lagrange points). In deep space it keeps the last system. If it guesses wrong, set the System box manually.

## Hotkeys (built in)

Starboard has its own hotkeys while it is running. Nothing else to install.

- **F8**: a small box pops up on top of the game. Type a scan signature and press Enter; the result shows on the overlay and you are put back in the game. Esc cancels.
- **F9**: sends `/showlocation` to the game chat for you.
- **F10**: auto-repeat on/off. Sends `/showlocation` every 10 seconds (change it in SETTINGS > MAP DATA) while Star Citizen is the active window. It briefly opens chat each time, so turn it off before a fight.

The chat panel must be visible in game for F9/F10 (press F12).

**If a hotkey seems to do nothing**, look at the F8, F9 AND F10 KEYS line in SETTINGS > MAP DATA (and the top right of the overlay). It shows what happened on every key press:

- *"F9 received, but the active window is ..."*: click into the game first.
- *"F9: /showlocation sent."* but nothing is typed in game: Star Citizen is running with administrator rights, which blocks keys from normal programs. Click **RESTART AS ADMIN** in SETTINGS > MAP DATA to restart Starboard with administrator rights.
- Nothing changes at all: the key did not reach Starboard. Make sure the hotkeys box is ticked, and close any old AutoHotkey script (right-click the green H in the system tray > Exit) so it does not grab the keys first.
- Letters missing in chat: open `user\settings.json` and raise `"key_delay_ms"` (default 30) and `"chat_open_ms"` (default 250), then restart the app.

More hotkeys, all changeable in SETTINGS > HOTKEYS (letters and numbers need Ctrl, Shift or Alt):

- **Ctrl+Shift+S**: show or hide Starboard.
- **Ctrl+Shift+1** to **9**, then **0**: open the tabs in the order they sit on the tab bar: HOME, LIVE, NAVIGATE, MINE, SALVAGE, HAUL, COMBAT, MISSIONS, SHOP, CRAFT. HANGAR, MONEY, EVENTS and SETTINGS have no key at first; give them one under SETTINGS > HOTKEYS. If you changed a key yourself, it stays as you set it.

Older versions used a separate AutoHotkey script for these keys. It is no longer needed.

## Nyx coverage

Nyx is only partly in the game. The app has the Nyx star, Nyx I, II and III, Delamar, the Castra and Pyro jump points, and the 10 QV Breaker Stations. It also knows when you are inside the Glaciem Ring or the Keeger Belt and has their mining lists.

- Levski and the People's Service Stations have no public coordinates yet. Fly to Levski once and use **SAVE SPOT** so it shows up from then on.
- Delamar's position comes from StarMap (patch 4.4 data) and has not been checked in game. If Levski readings look off, tell me what the app shows.

## Files

| File | Purpose |
| --- | --- |
| `sc_locator.py` | The app window and overlay |
| `core.py` | Coordinate math, speed and ETA, ore finder, sharing, data loading |
| `data_update.py` | Downloads and checks new data, makes backups |
| `signatures.py` | Signature identifier |
| `ocr_reader.py` | Screen reader (Windows text recognition) |
| `hotkeys_win.py` | Built-in F8/F9/F10 hotkeys |
| `hauling.py` | Trade routes, contract planning and UEX downloads |
| `ledger.py` | The money ledger |
| `hangar.py` | My Hangar |
| `shop.py` | Shop finder |
| `refining.py` | Refinery job timers |
| `combat.py` | Bounties and combat zones |
| `gamelog.py` | Finds and reads Star Citizen's Game.log |
| `wikidata.py` | Mining gear and missions from the Star Citizen Wiki API |
| `mydata.py` | Your own database built from the game log |
| `shipbuild.py` | Ship builder: ships' slots, parts and their stats (Wiki API) |
| `crafting.py` | Blueprints, the contracts that give them and the materials they need (Wiki API) |
| `gametext.py` | Reads the game's own text (names, contract briefings) from a text mod or Data.p4k |
| `data\signatures.json` | Signature values for every rock, deposit, harvestable and salvage type |
| `data\bodies.csv` | Planets, moons, Lagrange and jump points with rotation data |
| `data\locations.csv` | Outposts, caves, stations, landing zones and other locations |
| `data\ores.json` | Mineables per body and Nyx belt |
| `data\orbital_markers.json` | Orbital marker heights for each planet and moon |
| `data\backups\` | Copies of the data from before each update (created by the first update) |
| `user\` | Your saved spots, mining log, calibrations, contracts, current run, ledger, hangar, refinery jobs, bounties, game log progress, overlay position and fix history (created on first use) |
| `user\uex\` | Downloaded prices, terminals and ships |

## Limits

- Caves: the public location data only includes a few caves. Save the ones you find.
- Signature values are for patch 4.10.x. If a patch changes them, use TEACH or tell me and I will update the table.
- Ore data is for patch 4.10.x from the Star Citizen Wiki API. Clio, Vatra, Keeger Belt and QV Breaker Station entries are partial. Stanton and Pyro asteroid belts are not included.
- The data update needs internet access. If the app sits in a protected folder like Program Files, Windows may block the update from writing; keep it in Documents or similar.
- Speed and ETA are only as fresh as your last two fixes. ETA is shown for targets on the same planet or moon; for other bodies, follow the quantum route.
- Day and night times ignore terrain, and the Nyx planets and Delamar have no day cycle data yet.
- Click-through for the overlay works on Windows only.
- Trade prices are reported by players to UEX, so they can be out of date or missing for some terminals. Check the price at the terminal before you buy. A few terminals UEX lists are not on Starboard's map yet; routes still show them, but without a distance.

## Credits

- Stanton and Pyro coordinates: VerseTime by dydrmr (GPL-3.0), compiled from game files by the Murphy Exploration Group.
- Nyx coordinates and orbital marker heights: StarMap (starmap.space) read-only API.
- Coordinate method based on community navigation tools by Valalol and Graupunkt (Project Jericho).
- Ore and signature data, mining gear stats, missions and contract rewards: Star Citizen Wiki API (api.star-citizen.wiki).
- Trade, item, ship, fuel and refinery prices, terminals and ship details: UEX Corp (uexcorp.space) public API.
- News: RSI server status (status.robertsspaceindustries.com), RSI's Star Citizen YouTube channel feed, and Comm-Links through the Star Citizen Wiki API.
- Caves and extra surface places: Star Citizen Location Finder (quattrobaje3na-png.github.io/Star-Citizen-Location-Finder, featured on citizen-starter-guide.com).

Released under GPL-3.0 (see `LICENSE-GPL3.txt`).

## Disclaimer

Starboard is an unofficial Star Citizen fan tool, made by the community for the community. It is not affiliated with, endorsed by or sponsored by the Cloud Imperium group of companies. Star Citizen®, Squadron 42®, Roberts Space Industries® and Cloud Imperium® are registered trademarks of Cloud Imperium Rights LLC. All game content, names and images belong to Cloud Imperium Games and Roberts Space Industries. Other data belongs to its sources, credited above.
