# MD QC Agent — site preparation

One page for the lab, to have ready before installing. With this done, the
install takes about 15 minutes per instrument PC. The full guide is
[INSTALL.md](./INSTALL.md).

## Before the visit

| # | Have ready | Who / where | Notes |
|---|---|---|---|
| 1 | **Instrument PC** running Windows 10 or 11 (64-bit), ~2 GB free disk | Lab | The PC that receives the `.raw` files, or one that can read the folder they are written to |
| 2 | **A Windows account** on that PC for whoever uses it day to day | Lab / IT | No administrator rights needed. Admin is needed only to install for all users |
| 3 | **Skyline (64-bit)** installed from <https://skyline.ms> | Lab | Use the regular installer, not the ClickOnce (web) one. Daily or release builds both work |
| 4 | **The folder each instrument writes `.raw` files to**, e.g. `D:\Data\QC` | Lab | One folder per instrument. A mapped drive works; prefer the UNC path (`\\server\share\…`) if the PC has more than one instrument |
| 5 | **An instrument ID** for each instrument, e.g. `Astral_0001` | Lab | A label of your choosing; it is how runs are grouped on the platform |
| 6 | **The spectral libraries** (`.blib`, ~210 MB) for the SPDs you run | Mass Dynamics | The Skyline method and report ship with the agent; the libraries are copied in separately |
| 7 | **A Mass Dynamics API token** | Mass Dynamics platform, *Account Details* | Optional: without one the agent runs as a local QC monitor and uploads nothing |
| 8 | **Outbound HTTPS (port 443) to `app.massdynamics.com`** | IT | Only if uploading. Nothing listens for incoming connections; the dashboard is local to the PC |
| 9 | **The setup program** on a USB stick | [Latest release](https://github.com/MassDynamics/md-qc/releases/latest): `MDQC-Setup-<version>.exe` | No internet, Python or PowerShell needed on the instrument PC |

## On the day

1. **Install.** Double-click the setup program. If Windows shows "Windows
   protected your PC", choose *More info > Run anyway*; the setup program is
   not yet code-signed. It installs, starts the agent with a tray icon, and
   opens the dashboard. The agent starts at every login from then on.
2. **Check Skyline.** *Start menu > Mass Dynamics QC > MD QC Diagnostics*
   should show Skyline as found. If it doesn't, set the path to
   `SkylineCmd.exe` under *Settings > Skyline*.
3. **Copy the libraries** into `C:\ProgramData\MassDynamics\QC\methods\`,
   next to `QC_Method.sky`.
4. **Add each instrument** under *Settings*: its ID and the watch folder from
   items 4 and 5. Save.
5. **Add the token** under *Settings > Cloud* (item 7), choose
   *Production*, and save.

## Naming QC runs

The agent tells QC runs apart from samples by the file name. Put one of these
in the name, separated by `_`, `-`, `.` or a space:

| In the name | Run type |
|---|---|
| `PCD96`, `PCD384` (or `PCD`) | Process Control Digest; the number records the kit |
| `SSC` | System Suitability Control |
| `SSCBASE` (or `SSCGOLD`, `SSC0`) | Gold-standard run, for the baseline |
| `BLANK` | Blank |

Example: `SSCBASE_200SPD_S00618_r01.raw`. Anything else is treated as a
sample and not reported. *Settings > File names* shows the full list and
takes extra rules for a lab's own names.

## Recording the baseline

Each instrument needs a gold-standard baseline per SPD before its runs are
scored and uploaded.

1. Acquire **15–20 `SSCBASE` runs** at each SPD you use, at install and after
   a column change.
2. Open **Gold standards** in the dashboard, tick the representative runs,
   and **Save baseline**.

Until the baseline is saved, PCD and SSC runs are processed but held on the
PC, and a red banner says so. Saving releases them, scored against the new
baseline.

## It's working when

- The dashboard lists each instrument, and a new QC run appears within about
  90 seconds of the `.raw` file finishing.
- *Targets* reads e.g. `48/48`; `0/48` means the method or libraries don't
  match the acquisition (see [INSTALL.md §8](./INSTALL.md#8-troubleshooting)).
- With a token, the upload queue empties and the runs show on the platform.

If something is wrong, [INSTALL.md §9](./INSTALL.md#9-what-to-send-back-to-mass-dynamics)
lists what to send to Mass Dynamics.
