# HEDGECLOCK LCD mode

`lcd-clock.py` drives a physical Turing/UsbMonitor rev. A USB LCD with a live render of the
[HEDGECLOCK](https://annoyingmouse.js.org/WireFrameJS/000-MISCELLANEOUS/HEDGECLOCK/) browser clock,
without touching the normal hosted web page at all.

## How it's different from the hosted web version

- The hosted page (`index.html`) is completely unchanged and has no knowledge of the LCD bridge.
- LCD mode uses a separate page, `lcd.html`, which renders the same clock scaled and letterboxed into
  480x320 (the LCD's landscape resolution) and has all sound disabled.
- `lcd.html` posts its canvas to a small local HTTP bridge (started by `lcd-clock.py`), which decodes
  the frame, works out what actually changed since the last update, and writes only that to the screen.

## Requirements

- Windows (this has only been built/tested on Windows; the CLI itself has no Windows-only code, but the
  personal `--web-dir` default is a Windows path)
- Python, with this project's `requirements.txt` installed (Pillow and numpy are already required by
  the base project; no extra dependencies are needed)
- A Turing/UsbMonitor rev. A display
- A checkout of the HEDGECLOCK source (a separate project) containing `lcd.html`
- A Chrome or Edge install (used to render `lcd.html` automatically - see below)

**Important:** close TURMO/UsbMonitor first - only one application can use the serial port at a time.

## Running

```powershell
py -3 lcd-clock.py --port COM6
```

No browser window needs to be opened by hand: by default, `lcd-clock.py` automatically launches its own
**headless** Chrome/Edge instance pointed at `lcd.html`, so the clock is fully self-contained from a
single command. Stop with Ctrl+C - this closes the auto-launched browser, finishes any in-flight LCD
write, closes the serial connection and shuts the bridge down; the last frame shown stays on the screen.

### Browser launch options

```text
--open-browser    # launch the auto-managed browser VISIBLY instead of headlessly (to watch it render)
--no-headless     # don't auto-launch any browser - wait for one to be opened manually instead
--browser-path    # path to a specific Chrome/Edge executable, overriding auto-detection
```

Auto-detection checks common Chrome install locations first, then Edge. If neither is found, it prints
a warning and falls back to waiting for a manually-opened browser (the same as `--no-headless`) - the
bridge still works fine if you open the printed URL yourself.

The auto-launched browser always uses its own temporary profile (`--user-data-dir`), so it's completely
independent of - and never interferes with - any browser window you already have open, and is cleanly
terminated (not left running) on shutdown.

If HEDGECLOCK isn't at the default location, point `--web-dir` at the folder containing `lcd.html`:

```powershell
py -3 lcd-clock.py --port COM6 --web-dir "C:\path\to\HEDGECLOCK"
```

### Brightness and COM port

```powershell
py -3 lcd-clock.py --port COM6 --brightness 15
py -3 lcd-clock.py --port AUTO
```

`--port AUTO` auto-detects the display by its USB serial number/VID/PID. Keep brightness modest on
rev. A hardware - it can get warm at higher levels.

### Hardware test pattern

Validates the physical display path independently of HEDGECLOCK/the browser:

```powershell
py -3 lcd-clock.py --port COM6 --test-pattern
```

Cycles through black, white, red, green, blue, a checkerboard and a text frame.

### Benchmark

Measures real transfer times for a full frame and several partial-update sizes:

```powershell
py -3 lcd-clock.py --port COM6 --benchmark
```

Measured on the reference hardware (rev. A / USBMONITOR_3_5, 480x320 landscape):

| Update | Bytes (RGB565) | Elapsed | Updates/sec |
|---|---|---|---|
| Full 480x320 | 307,200 | 1.205 s | 0.83 |
| Region 240x160 | 76,800 | 0.301 s | 3.32 |
| Region 120x80 | 19,200 | 0.075 s | 13.30 |
| Clock-digit-sized 118x73 | 17,228 | 0.068 s | 14.77 |

Cost scales roughly linearly with the number of pixels sent, which is why the dirty-region strategy
below is worth doing: HEDGECLOCK's own animation only redraws once a second, and in practice most of
those redraws only touch a single digit's ~60x150px region (or two digits around a minute/hour
rollover), so real updates typically complete in well under 100ms - comfortably inside the default
250ms budget, with the full-frame path (~1.2s) reserved for the first frame or a genuinely large change.

## Dirty-region strategy

The bridge keeps the last frame it actually wrote and, for each new frame, computes the padded
bounding box of pixels that changed by more than a small per-channel tolerance (ignores antialiasing
noise). If that box covers more than a configurable fraction of the screen (default 60%), it sends a
full frame instead - otherwise it sends just the cropped region via `DisplayPILImage`.

```text
--update-ms 250              # minimum time between LCD writes
--full-frame-threshold 0.60  # dirty-area fraction above which a full frame is sent
--pixel-threshold 10         # per-channel tolerance before a pixel counts as "changed"
```

Only ever one frame is "in flight" and one pending: if the browser submits new frames faster than the
bridge can write them, the older pending frame is discarded and only the newest is kept - the display
never accumulates a backlog and always shows the most recent state.

## Other options

```text
--host 127.0.0.1     # bridge bind address (never exposed beyond localhost by default)
--port-http 8765      # bridge HTTP port
--reset-on-exit         # clear the LCD on shutdown instead of leaving the last frame shown
--debug                  # verbose logging
```

See "Browser launch options" above for `--open-browser`, `--no-headless` and `--browser-path`.
