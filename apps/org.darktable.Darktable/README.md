# darktable (with AI Subsystem Enabled)

Flatpak package for [darktable](https://www.darktable.org/), based on [`flathub/org.darktable.Darktable`](https://github.com/flathub/org.darktable.Darktable) and [PR #252](https://github.com/flathub/org.darktable.Darktable/pull/252), compiled with `onnxruntime` and `-DUSE_AI=ON` (`-DONNXRUNTIME_OFFLINE=ON`) to enable the optional AI subsystem (AI masking, denoising, and upscaling).

## Installation

```bash
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak remote-add --if-not-exists luzechao https://luzechao.github.io/flatpak/flatpak.flatpakrepo
flatpak install luzechao org.darktable.Darktable
```
