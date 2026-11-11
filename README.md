# Radio Link Planner

**English** | [Português (Brasil)](README.pt-BR.md)

A local planning tool for **terrestrial VHF/UHF point-to-point links and coverage**. It combines terrain profiles, propagation models, a bidirectional link budget, uncertainty analysis and traceable technical reports. The repository includes a Windows desktop interface and a scientific command-line engine.

**Author:** Mario Pin, PU2PTU · **Application:** 0.5.1

## What it can do

| Area | Capabilities |
| --- | --- |
| Point-to-point link | Enter two stations, radio settings and a target availability; view terrain, Earth curvature, first Fresnel zone, obstructions, propagation losses and margins in both directions. |
| Propagation models | Compare the **NTIA ITM 1.3**, **ITU-R P.1812-8** and **ITU-R P.2001-6** implementations where applicable. P.1812 is limited to 1–50% time; it is not extrapolated to higher availability. |
| Coverage | Calculate a P.1812 result for each cell center from 250 m outward, using an independently sampled Copernicus GLO-30 terrain path. Display a heatmap and 0/+3/+6/+12 dB margin contours. |
| Uncertainty | Reproducible Monte Carlo for equipment and installation uncertainties, without adding an arbitrary second atmospheric variation. |
| Workflow | Desktop project New/Open/Save, map coordinate picker, progress/time/memory estimates, cancel and resume, and reuse of physical loss when only link-budget inputs change. |
| Output | JSON, Markdown, HTML, PDF, terrain and Monte Carlo plots, interactive coverage map and scientific metadata. |

The interface offers Portuguese, English, Spanish, French and German. Computations run locally. The coordinate picker/report viewer may temporarily serve pages on **127.0.0.1** for display; this is a local loopback service.

## Hardware and input data

**No electronics or pin connections are needed.** This is a planning application, not a controller connected to a transmitter. To model a real station, gather the following measured or specified inputs for **each end**:

| Input | Examples / meaning |
| --- | --- |
| Location | Latitude/longitude, entered directly or selected on the map. |
| Antenna | Height above ground, gain in dBi, polarization and pointing. |
| Radio and line | Transmit power, cable/connector loss and receiver noise/threshold. |
| Link target | Frequency, mode (FM, SSB, CW, APRS or LoRa) and availability goal. |
| Terrain | Downloaded **Copernicus GLO-30** tiles or an explicitly supplied profile CSV. |

Inputs represent a proposed installation; the software does not measure the antenna, noise floor or feed-line loss for you. Internet is needed for the first download of terrain and ITU digital maps for a new area. Cached data permit later calculations for the same locations. OpenStreetMap tiles are for visual context and do not participate in the propagation calculation.

## Installation and libraries

For normal Windows use, get the available **Windows x64 installer or portable ZIP** from [Releases](https://github.com/mariopin80/Radio-Link-Planner/releases). The packaged application includes its Python dependencies; keep all files together when using the portable ZIP. No separate Python installation is needed for the packaged program.

To develop or run from source, use **Python 3.10+** and install the optional groups defined in [`pyproject.toml`](pyproject.toml). A C++17 compiler is needed to build the bundled NTIA ITM library (`MSVC cl` from a Developer Command Prompt on Windows); Git is needed to fetch the pinned Py1812/Py2001 packages. Core dependencies are **NumPy, Pydantic and ReportLab**; extras add **Matplotlib** (plots), **Rasterio** (geospatial terrain), **Py1812/Py2001** (propagation models), **PyWebView/PyInstaller** (desktop/build) and **pytest/pypdf** (development). On Windows, use a Developer Command Prompt with MSVC available:

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,plots,geo,models,desktop]"
.venv\Scripts\python.exe scripts/build_itm.py
.venv\Scripts\python.exe scripts/bootstrap_itu_data.py
```

Run the two build/data scripts from a suitable development shell. `bootstrap_itu_data.py` obtains official ITU digital products for local use; these full datasets are **not stored in the repository**. For a CLI-only installation, omit `desktop` if appropriate, but keep the model and data components required by the analysis you run.

## Desktop guide

### First point-to-point link

1. Launch `RadioLinkPlanner.exe`, select **English** using the language flags if needed, choose **Point-to-point link** and create a new project. Enter both station coordinates directly or choose locations on the map.
2. Set frequency, mode, polarization, desired availability, antenna heights/gains, line losses, transmit powers and receiver thresholds for both terminals.
3. Choose the output folder and Monte Carlo run count under **Analysis and results**; select **Get terrain and analyze**. The app downloads missing terrain and model data as needed, caches them, then runs the analysis.
4. Open **Map and report** for the path, profile, Fresnel clearance, model comparison, margins and recommendations. Save the project to repeat or edit it later.

### Coverage map

1. Choose **Coverage map**, enter the transmitting station and reference receiver settings, and select radius **50–500 km** and a quick/recommended/detailed/custom grid.
2. Check the predicted cell count, memory and processing time, then start the calculation. Each cell at least 250 m away has its own P.1812 path; closer cells use free-space loss and are reported separately.
3. Follow progress. Cancel if necessary: repeating the same physical settings and output folder resumes completed blocks. Changes only to power, gain, line loss or sensitivity can reuse stored propagation loss; changes to path/model settings require recalculation.
4. Open the resulting heatmap, contours and technical report.

Large radii can take hours and use substantial storage even when the total cell count is similar. Terrain profiles are sampled nominally at 30 m regardless of map cell size. Results live under the user profile; terrain and ITU caches under `%LOCALAPPDATA%\RadioLinkPlanner\` on Windows.

## Command line and example outputs

The included Morro do Jacu–Palmira example points to a checked-in terrain profile and can be run without retrieving a new profile:

```sh
radio-link analyze examples/morro_jacu_palmira.json --output results/morro_jacu_palmira
```

The CLI accepts `--runs`, `--no-plots` and `--print-json`. `radio-link-desktop` starts the desktop app from a development environment. The reproducible example artifacts are in [`demo-output/`](demo-output/):

![Terrain profile from the included example](demo-output/profile.png)

![Monte Carlo model comparison from the included example](demo-output/monte_carlo.png)

| Point-to-point output | Content |
| --- | --- |
| `result.json`, `summary.md` | Full numerical result and engineering summary. |
| `report.html`, `relatorio_enlace.pdf` | Visual report and printable technical report. |
| `profile.png`, `monte_carlo.png` | Terrain/Fresnel profile and probability comparison. |

Coverage adds `coverage_project.json`, margin/loss `.npy` grids, propagation/metadata JSON, heatmap/overlay PNG, contour GeoJSON, HTML and PDF reports. The demo output is a recorded example; the current engine may generate different figures as algorithms and inputs evolve.

## Scientific scope

The current desktop focus is **30–3000 MHz** and **3–1000 km** terrestrial paths. Automatic terrain profiles currently assume inland land along the path and omit vegetation/buildings; coastal or over-water paths need review of `zone_code`. DEM error and height error are not sampled by the current Monte Carlo. Treat model agreement and margins as engineering estimates, then compare with measured equipment parameters and field observations. See [scientific scope](docs/scientific-scope.md) and the [reference case](tests/reference/morro_jacu_palmira/reference_notes.md).

Third-party code and data retain their own notices, including [`vendor/`](vendor/) and the official ITU/Copernicus sources. No project-wide license file is present in this repository.
