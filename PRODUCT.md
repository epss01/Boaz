# Boaz

## Platform
Local web dashboard on Windows, controlling one explicitly selected BlueStacks 5 instance.

## Stack
User approved Python 3.11, uv, Airtest, NiceGUI, pytest, and Tesseract/pytesseract.

## Users and purpose
A Clash of Clans player configuring repetitive Home Village farming. Separate simulation and live actions; live mode recognizes screens and verifies calibrated collection, prepared-army deployment, observed results, and wall upgrades.

## Confirmed constraints
One account, English game UI, named JSON presets, one calibrated landscape resolution. No gem spending, remote access, database, or plugin system. Wall upgrades use user-marked targets and default off. Ordered troops, heroes, and spells; no manual hero abilities. Simulation and observed live data must be visibly distinct.

## Success
The dashboard starts without an emulator. Settings persist, controls work, simulation never sends input, and a connected emulator can supply screenshots. The approved implementation plan is the product brief.
