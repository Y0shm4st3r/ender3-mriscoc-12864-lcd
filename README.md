# Ender3V1-427-BLT — reproducible MRiscoC build for a monochrome-LCD Ender 3

[Marlin 2.1.4 / MRiscoC Professional Firmware](https://github.com/mriscoc/Ender3V2S1) compiled for
an **Ender 3 V1** with a **Creality v4.2.7** board, the **stock CR10 12864 monochrome LCD**,
a generic BLTouch clone, a direct-drive extruder and dual Z.

## Why this repo exists

MRiscoC ships prebuilt binaries, and for most Ender 3 V2 / S1 machines you never need a toolchain.
**This hardware combination is not covered by any of them.** Every MRiscoC release targets the DWIN
colour touchscreen. There is no release binary for a v4.2.7 board driving the stock 12864 monochrome
LCD — the blue-and-white screen the V1 shipped with.

So compiling is not a preference here. It is the only path to running this firmware on this display,
and it shows up directly in the diff: **four of the twelve changed lines exist purely to select the
right screen** (`RET6_12864_LCD`, `CR10_STOCKDISPLAY`, `DWIN_LCD_PROUI` off, and the backlight
timeout that the monochrome panel cannot support).

Once you are compiling anyway, the second reason takes over: **being able to rebuild the exact binary
that is running on the machine.** This is not a pile of tweaks — it is a closed, verified identity
chain.

```
Marlin/Configuration.h  +  Marlin/Configuration_adv.h
        │   12-line diff against MRiscoC Ender3V2S1-20260106
        │   platformio.ini → default_envs = STM32F103RE_creality
        ▼
firmware/firmware-20260919-212756.bin
        │   sha256  27e0c2afb9818fcf1c2a6c4a65bfe58aa3ec2f31f004679fa76c7885ff98861c
        ▼
M115 → "Marlin 2.1.4 MRiscoC ... (Sep 19 2026 21:27:52)"
       MACHINE_TYPE: Ender3V1-427-BLT
```

That timestamp is embedded in the `.bin` by the compiler and reported back by the machine. They
match. That is what turns "I think this is what I flashed" into a verifiable fact.

---

## Target hardware

| Subsystem | Component | Note |
|---|---|---|
| Board | Creality v4.2.7 | MCU is **STM32F103RE** — not RC. This decides the build environment |
| MCU | STM32F103RE, 512 KB flash | |
| Display | **Stock CR10 12864 monochrome** | `RET6_12864_LCD` + `CR10_STOCKDISPLAY`. This is the reason for building from source |
| Probe | **Generic BLTouch clone** | Not Antclabs. See the 5 V note below |
| Extruder | Direct drive | `E_STEPS 93` |
| Hotend | Stock Creality | PID: `M301 P22.89 I1.87 D70.18` |
| Z axis | Dual, driven through a **splitter** | Both motors on one driver. See the `G34` limitation |
| Fan duct | [Satsana 5015 remix by Scrath](https://www.printables.com/model/140833) | Bracket **V2** → offset X−43.65 |
| USB | CH340 | `BAUDRATE 250000` |

---

## Building

### 1. Clone the base at the right tag

```bash
git clone https://github.com/mriscoc/Ender3V2S1.git
cd Ender3V2S1
git checkout Ender3V2S1-20260106
```

`git checkout <tag>` puts the tree at that exact commit. Without the tag you get `main`, which moves,
and the build stops being reproducible. **The tag is part of the recipe, not a detail.**

### 2. Replace the two configuration files

```bash
cp /path/to/this/repo/Marlin/Configuration.h      Marlin/Configuration.h
cp /path/to/this/repo/Marlin/Configuration_adv.h  Marlin/Configuration_adv.h
```

These are the **only** two modified files. Verified: `Marlin/src/lcd/e3v2/proui/proui_ex.h` is
byte-identical to upstream.

### 3. Pin the build environment

In `platformio.ini`, at the repo root:

```ini
default_envs = STM32F103RE_creality
```

> **The trap that costs the most time.** The near-identical environment `STM32F103RC_creality` is for
> the **RC** MCU (256 KB). It compiles without a single error and produces a `.bin` that **bricks** a
> v4.2.7 board on boot, because the memory layout and bootloader offsets do not match.
> **RE, not RC.** Confirm it by reading the chip: the package is marked `STM32F103RET6`.

### 4. Compile

```bash
pio run
```

`pio run` builds the environment named in `default_envs`. Output:

```
.pio/build/STM32F103RE_creality/firmware.bin
```

Compare against the binary in this repo:

```bash
sha256sum .pio/build/STM32F103RE_creality/firmware.bin
```

> The hash **will not** match `27e0c2af…`. The compiler embeds the build date and time
> (`__DATE__` / `__TIME__`), so every build produces a different binary even from identical sources.
> What should match is the **size** (within a few bytes) and the behaviour. The included `.bin` is the
> machine's reference, not a bit-for-bit target.

---

## Flashing

1. Rename the `.bin` to something you have **never used before** (e.g. `fw-0920.bin`). Creality's
   bootloader compares the filename against the last one it flashed and **skips the flash if they
   match.** This is the number one cause of "I flashed it and nothing changed".
2. SD card formatted **FAT32**, **4096-byte** clusters, ideally ≤ 8 GB.
3. `.bin` in the root, printer off, insert the card, power on.
4. Wait ~15 s. The screen stays blank during the flash — that is normal.
5. Confirm with `M115`.

### 5. Mandatory after flashing

```gcode
M502   ; load the firmware's compiled defaults into RAM
M500   ; write them to EEPROM
```

**Flashing does NOT clear the EEPROM.** It is non-volatile storage independent of the firmware, and
at boot the EEPROM **overrides** the compiled defaults. Skip this and you are running the old values
under new firmware — and you will spend hours debugging a configuration file the machine never read.

Analogy: compiling changes the spec sheet. The EEPROM is the adjustment somebody already made to the
screw. Changing the paper does not turn the screw.

Expected confirmation: `Settings Stored (778 bytes; crc <n>)`

### 6. Recalibrate the Z offset — not optional

```gcode
G28                ; home all axes
M851 Z0            ; clear the offset so you measure from zero
G1 Z0 F300         ; bring the nozzle down to the Z=0 plane
                   ; now step down with babysteps until paper just drags
M851 Z<value>      ; the negative value you found
M500
```

The `NOZZLE_TO_PROBE_OFFSET` in this repo carries **Z −0.29**, which is **specific to this assembly**.
It depends on how far the BLTouch pin protrudes relative to the nozzle tip, and it changes if you
re-seat the sensor, swap the hotend, or wear the nozzle down.

**X and Y are reproducible**: they come from the geometry of the printed bracket (Satsana V2). Anyone
who prints that bracket gets `X −43.65  Y −10.00`.

---

## The 12 changes against upstream

Base: `configurations/Ender3V2-422-BLT/` from tag `Ender3V2S1-20260106`.

### `Configuration.h` — 9 lines

| Directive | Value | Why |
|---|---|---|
| `RET6_12864_LCD` | enabled | `pins_CREALITY_V4.h` uses it to select the pin mapping for the RET6 variant of the 12864 LCD. Without it: blank screen or garbage |
| `MOTHERBOARD` | `BOARD_CREALITY_V427` | Selects the pin map. Must pair with the `STM32F103RE_creality` environment |
| `CUSTOM_MACHINE_NAME` | `"Ender3V1-427-BLT"` | Appears as `MACHINE_TYPE` in `M115`. This is the identifier that distinguishes this build |
| `NOZZLE_TO_PROBE_OFFSET` | `{ -43.65, -10.0, -0.29 }` | Geometry of the Satsana V2 bracket. The V1 bracket would give X−42.00 |
| `Z_PROBE_FEEDRATE_FAST` | `(8*60)` ← `(16*60)` | At 16 mm/s the generic BLTouch could not deploy the pin in time for the second touch. That is a mechanical limit of the solenoid, not a software one |
| `Z_CLEARANCE_BETWEEN_PROBES` | `8` ← `5` | With the bed tilted, 5 mm of clearance was not enough at the corners |
| `LCD_PROBE_Z_RANGE` | `10` ← `4` | Insufficient range against the tilt actually measured |
| `CR10_STOCKDISPLAY` | enabled | Stock monochrome panel |
| `DWIN_LCD_PROUI` | **disabled** | This is for the DWIN colour screen on the V2 / S1. This machine is a V1 |

### `Configuration_adv.h` — 3 lines

| Directive | Value | Why |
|---|---|---|
| `BLTOUCH_DELAY` | `500` | Gives the solenoid time to retract the pin between mesh points |
| `BLTOUCH_HS_MODE` | `false` | **The most important change.** In High-Speed mode the probe does not retract between points; if one deploy fails, the error accumulates silently and contaminates the mesh without raising anything |
| `LCD_BACKLIGHT_TIMEOUT_MINS` | disabled | Requires `LCD_BACKLIGHT_PIN` or a DWIN panel. The CR10 monochrome LCD supports neither |

---

## Known traps

### `M115` reports two names, and one of them lies

```
FIRMWARE_NAME:Marlin 2.1.4 MRiscoC Ender3V2-422-MM, based on bugfix-2.1.x
MACHINE_TYPE:Ender3V1-427-BLT
```

`Ender3V2-422-MM` comes from `Marlin/Version.h` line 40, which was **deliberately left unmodified**,
so that the build still reproduces from two files and nothing else.
**Only `MACHINE_TYPE` reflects this configuration.** `FIRMWARE_NAME` is upstream's generic label. If
you document the machine by `FIRMWARE_NAME`, you are documenting something else.

### `G34` does not exist on this machine

`Z_STEPPER_AUTO_ALIGN` requires **two independent drivers** so one motor can be moved relative to the
other. With a splitter, both motors share a driver and receive identical step pulses: mechanically
they are one axis. Gantry levelling is **manual** — loosen one coupler and turn that leadscrew by hand.

### OrcaSlicer can contaminate the EEPROM

OrcaSlicer emits `M201` / `M203` / `M204` in the header of **every** g-code file. On their own they
are per-job and vanish at the next power cycle. But if the start g-code contains an `M500`, every
print writes the slicer's limits to EEPROM permanently — and burns one write cycle of the emulated
flash. Neither piece is a fault by itself; the pair is.

**Never put `M500` in start g-code.** To check for contamination, compare `M503` against this table:

| Value | Firmware default | Symptom if OrcaSlicer wrote it |
|---|---|---|
| `M203 E` | `45.00` | `60.00` |
| `M201 E` | `1000.00` | `5000.00` |
| `M204 R` | `800.00` | `1000.00` |
| `M204 T` | `1000.00` | `500.00` |

If they do not match: `M502` + `M500`, and remove the `M500` from start g-code.

### Generic BLTouch and 5 V mode

Clones are often 5 V-only, unlike the Antclabs v3.x which auto-detects. This build does **not** enable
`BLTOUCH_SET_5V_MODE`. If your clone does not trigger reliably, that is the first switch to try — but
measure the signal pin voltage first: forcing 5 V onto a board expecting 3.3 V can damage the MCU input.

### Pasting multiple commands into a serial console

Some consoles concatenate consecutive pasted lines into a single transmission. Marlin's parser takes
the first valid code it finds on a line, executes it, replies `ok`, and **discards the rest silently**.
`M420` followed by `G29` arrives as `M420G29`, the leveling state is reported, and the probe never
runs — with no error anywhere. Send state-changing commands **one at a time**, waiting for each `ok`,
and verify with `M503` rather than trusting the acknowledgement.

---

## Verification

```gcode
M115    ; identity chain: the timestamp should read "Sep 19 2026 21:27:52"
M503    ; full EEPROM dump: mesh, offsets, limits, PID
M851    ; probe offset in isolation
M420    ; leveling state. S1 = active. S0 = a mesh exists but is NOT applied
M48 P10 V2  ; probe repeatability: 10 samples, verbosity 2. Requires G28 first
```

`M48` is the only one that measures **quality** rather than configuration. It returns the standard
deviation of 10 probes at the same point. Reference for this machine: **σ = 0.0034 mm**.

- σ < 0.01 mm → probe is healthy
- σ > 0.02 mm → check sensor mounting, wiring, belt tension

It is the equivalent of putting a dial indicator on an axis: it does not tell you the axis is centred,
it tells you the measurement is trustworthy.

> **What `M48` does not measure.** It probes the same point repeatedly without moving X or Y, so it
> characterises the sensor, not the machine. The machine has its own, larger repeatability figures:
>
> | Measurement | Worst point-to-point difference | What it characterises |
> |---|---|---|
> | `M48 P10 V2` | σ 0.0034 mm | the sensor alone |
> | two `G29` back to back, same session | **0.015 mm** | the machine, short term |
> | two `G29` from different sessions | 0.063 mm | the machine, long term |
>
> Those are the thresholds for deciding whether a change between two meshes is real — not σ.

---

## Layout

```
Marlin/
  Configuration.h          the 9 modified lines
  Configuration_adv.h      the 3 modified lines
firmware/
  firmware-20260919-212756.bin
docs/
  mesh-analysis.py         separates tilt from warp in a G29 mesh
SHA256SUMS                 checksums for all three tracked artefacts
LICENSE                    GPL-3.0
```

Verify everything at once, from the repo root:

```bash
sha256sum -c SHA256SUMS
```

`-c` reads the file as a list of *expected* hashes and checks each path against it, printing `OK` or
`FAILED` per line. Paths inside are relative to the repo root, so run it from there.

### `docs/mesh-analysis.py`

A large mesh range tells you nothing on its own, because it mixes two defects that are fixed in
completely different ways: **tilt** (the bed or gantry mounted crooked — correctable with the
levelling knobs or the Z axis) and **warp** (the plate itself not being flat — not correctable by
tightening anything).

The script fits a least-squares plane to the mesh points and subtracts it. What is left — the
residual — is the real non-planar error.

```bash
# paste the `G29 W I.. J.. Z..` lines from M503 into a file
python3 docs/mesh-analysis.py mesh.txt
```

Real example from this machine. Raw range **1.938 mm**, which reads like a destroyed build plate.
Decomposed: a tilt of +9.79 mm/m along X, and a residual of only **0.163 mm** range (σ 0.043 mm)
across 180 mm. The prediction was that levelling would remove the tilt and leave the residual alone.

After equalising the Z leadscrews and re-tramming the corners:

| | Before | After |
|---|---|---|
| Raw mesh range | 1.938 mm | **0.180 mm** |
| Tilt along X | +9.79 mm/m | **+0.44 mm/m** |
| Non-planar residual | 0.163 mm | **0.131 mm** |
| Residual shape vs before | — | **r = 0.965** |

The tilt dropped 22×. The residual barely moved, and its map kept the same shape. That confirms the
residual belongs to the plate, not to the assembly. What remains is compensated by the mesh.

> A table with one short leg gets shimmed. A table with a warped top gets replaced. This one gets
> shimmed.

---

## Licence

The files under `Marlin/` are derivative works of **Marlin Firmware** and keep their original
copyright notice:

> Copyright (c) 2020 MarlinFirmware · GNU General Public License **v3.0 or later**

The upstream MRiscoC repository distributes its own `LICENSE` as **LGPL-2.1**. The headers of the
files included here carry a **GPL-3.0** notice, which is what applies to this redistribution, and is
the text shipped in `LICENSE`.

`docs/mesh-analysis.py` is original code, published under the same GPL-3.0 so that there is only one
licence in the tree.

- Marlin: https://github.com/MarlinFirmware/Marlin
- MRiscoC Professional Firmware: https://github.com/mriscoc/Ender3V2S1
- Satsana 5015 duct remix (Scrath): https://www.printables.com/model/140833
