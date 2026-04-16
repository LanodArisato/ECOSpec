# ECOSpec Setup Guide

This is the setup guide for running ECOSpec on a Raspberry Pi 5 with a 1024×600 touchscreen. ECOSpec runs as a native desktop app using Python and PyWebView, no browser needed.


## What you'll need

- Raspberry Pi 5 running Raspberry Pi OS (Bookworm, 64-bit)
- A 1024×600 touchscreen in landscape orientation
- An internet connection the first time you run it (to install dependencies)

## Getting started

If you've downloaded the zip on the Pi already, unzip it and you should have an `ecospec/` folder. The structure inside looks like this:

Folder Topology:
ecospec/
├── ecospec.py
├── ecospec@.service
├── README.md
├── run.sh
├── ui/
│   └── index.html
└── app/
    ├── app.py
    ├── hardware/
    │   ├── cameraControl.py
    │   └── espComms.py
    └── processing/
        ├── processing.py
        └── spectra/
            ├── lib/
            │   └── lib.csv
            ├── processed/
            └── raw/


Before you can run it, you need to make the launch script executable:
chmod +x ~/ecospec/run.sh


Then just run it:
~/ecospec/run.sh

The first time you run this it'll install the required packages (GTK, WebKit, pywebview) automatically, this takes a minute or two. After that it'll open the app. Every time after that, use:


~/ecospec/run.sh --run
The `--run` flag skips the dependency check and launches straight away.

Or

Exectue the run.sh by double clicking on it in the folder

## Fullscreen / kiosk mode

If you want the app to take up the whole screen with no window titlebar, open `ecospec.py` and change these two lines:

fullscreen=True,
frameless=True,

## Debug Mode

If you want to bypass actively using the ESP32, Acuros CAM, etc...
You can click on the ECOSpec logo in the top left 5 times to open a debug mode that allows you to process data from a .csv file
