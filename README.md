![Banner](img/banner.png?raw=true)
# Kefirosphere

Kefirosphere is a fork of the Atmosphere project featuring a set of specific system modifications designed to enhance hardware support and optimize resource management on the Nintendo Switch.

---

## Technical Specifications

The following is a detailed description of the modifications and features implemented in Kefirosphere compared to the upstream Atmosphere codebase.

### System UI and Identification
* **Boot Splash**: The standard Atmosphere logo has been replaced with a custom Kefirosphere splash screen at the `boot` and `fusee` levels.
* **Version String Integration**: The Kefirosphere version identifier is integrated into the System Settings and system error reports for easier build identification.
* **Daybreak OS Version Display**: The main menu of the Daybreak firmware update utility now displays the currently installed OS version.

### Hardware Support
* **DRAM Drivers**: Added support for newer LPDDR4X module revisions found in recent console batches, ensuring compatibility where standard drivers may fail.
* **Kiosk Unit Compatibility**: Initialization logic has been adjusted to ensure full functionality on demonstration (Kiosk) units.

### Execution and Compatibility
* **Signature Verification (ACID)**: ACID signature verification for homebrew is disabled. The project includes integrated signature patches ("sigpatches"), allowing installed content to run without external patch sets.
* **Legacy Homebrew Support**: Specific upstream changes in the kernel and loader that broke compatibility with older homebrew applications have been reverted to ensure a broader software support library.

### System Services and Logging
* **MicroSD Logging Removal**: Diagnostic logging to the SD card (via `erpt` and `fatal` services) has been disabled. This reduces microSD I/O overhead, improves performance, and extends the lifespan of the storage medium.
* **Save Redirection**: Implemented an optional mechanism to redirect user saves from internal NAND to the microSD card when operating in emuMMC mode.
* **Daybreak Safety Measures**: The Factory Reset function in Daybreak is disabled to prevent accidental data loss. Additionally, exFAT driver support is forced by default during every update.

### Resource Optimization
* **System Pool Adjustment**: The Non-Secure System Pool size has been reduced by approximately 1900 KB via `KSystemControl`. These resources are reallocated to the system to extend the capabilities of background processes.
* **emuMMC RAM Boost**: When booting into emuMMC, the system automatically releases 40 MB of RAM (typically reserved for the browser and Nintendo network services) for use by homebrew applications, such as emulators.

---

## Build Variants

The project supports the generation of specific build variants via the patch system:

1. **Overclocking (OC)**: Patches for `pcv` and `ptm` modules to unlock hardware frequency limits.
2. **8GB RAM Edition**: Configurations tailored for consoles with hardware-expanded 8 GB RAM.
3. **40MB Homebrew Boost**: Forces the 40 MB memory release for all system modes.

---

## Credits

Atmosphère is currently being developed and maintained by __SciresM__, __TuxSH__, __hexkyz__, and __fincs__.<br>
In no particular order, we credit the following for their invaluable contributions:

* __switchbrew__ for the [libnx](https://github.com/switchbrew/libnx) project and the extensive [documentation, research and tool development](http://switchbrew.org) pertaining to the Nintendo Switch.
* __devkitPro__ for the [devkitA64](https://devkitpro.org/) toolchain and libnx support.
* __ReSwitched Team__ for additional [documentation, research and tool development](https://reswitched.github.io/) pertaining to the Nintendo Switch.
* __ChaN__ for the [FatFs](http://elm-chan.org/fsw/ff/00index_e.html) module.
* __Marcus Geelnard__ for the [bcl-1.2.0](https://sourceforge.net/projects/bcl/files/bcl/bcl-1.2.0) library.
* __naehrwert__ and __st4rk__ for the original [hekate](https://github.com/nwert/hekate) project and its hwinit code base.
* __CTCaer__ for the continued [hekate](https://github.com/CTCaer/hekate) project's fork and the [minerva_tc](https://github.com/CTCaer/minerva_tc) project.
* __m4xw__ for development of the [emuMMC](https://github.com/m4xw/emummc) project.
* __Riley__ for suggesting "Atmosphere" as a Horizon OS reimplementation+customization project name.
* __hedgeberg__ for research and hardware testing.
* __lioncash__ for code cleanup and general improvements.
* __jaames__ for designing and providing Atmosphère's graphical resources.
* Everyone who submitted entries for Atmosphère's [splash design contest](https://github.com/Atmosphere-NX/Atmosphere-splashes).
* _All those who actively contribute to the Atmosphère repository._
