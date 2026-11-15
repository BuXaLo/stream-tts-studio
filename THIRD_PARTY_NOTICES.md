# Third-party notices and license inventory

**Status:** practical best-effort inventory; not a legal opinion or exhaustive SBOM  
**Last reviewed:** 2026-11-16  
**Applies to:** Stream TTS Studio source repository and the portable runtime described in [docs/PORTABLE_RUNTIME.md](docs/PORTABLE_RUNTIME.md).

## Scope

The root [MIT License](LICENSE) applies to original Stream TTS Studio code and documentation. It does not relicense third-party components bundled with the portable distribution.

The portable runtime was inherited from the CosyVoice 3 portable setup and subsequently updated for this project. This inventory records the main known components and the information collected from the actual runtime. It does not attempt to enumerate every transitive Python package individually.

## Portable base and main components

| Component | Known version / source | License information | Notes |
|---|---|---|---|
| Stream TTS Studio original code | Current repository revision | MIT | See root `LICENSE` |
| Original portable base | [mortimerme/repocollect](https://huggingface.co/mortimerme/repocollect), `cosyvoice3-0529.7z` | Contains third-party components under their respective licenses | Identified in project README as the starting point of the portable setup |
| CosyVoice | CosyVoice 3 | Apache-2.0 | Upstream project license; bundled dependencies retain their own licenses |
| Matcha-TTS | Upstream dependency of CosyVoice | MIT | Separate upstream component |
| Fun-CosyVoice3-0.5B-2512 | Model card | Apache-2.0 per official model card | Local model snapshot is not pinned as a whole to an immutable revision |
| Python | 3.10.11 | Python Software Foundation License | Portable interpreter; retain the license files supplied with the runtime |
| PyTorch | 2.7.1+cu128 | BSD-3-Clause | PyTorch distribution also contains notices/licenses for bundled components |
| CUDA / cuDNN | CUDA 12.8; cuDNN 9.7.1 in the recorded environment | NVIDIA license terms | NVIDIA components are subject to their own terms |
| FFmpeg | 7.1.1-full_build-www.gyan.dev | GPLv3 build | Exact local build details are recorded below |

## Runtime inventory snapshot

A read-only inventory was collected from the portable environment:

- Python version: **3.10.11**
- Installed Python distributions: **188**
- Files named `LICENSE`, `NOTICE`, `COPYING` or `EULA` found under the runtime: **284**
- Package metadata contains license information for most, but not all, distributions. Missing metadata is not treated as evidence that a package has no license.
- The runtime includes packages with different license families, including MIT, BSD, Apache-2.0, MPL-2.0, LGPL and vendor-specific terms. Their bundled license/notice files should be retained with the runtime.

Examples visible in the collected package metadata include:

| Package | Version | Declared license metadata |
|---|---:|---|
| torch | 2.7.1+cu128 | BSD-3-Clause |
| frozendict | 2.4.7 | LGPL v3 |
| lameenc | 1.8.4 | LGPL-3.0-or-later |
| soxr | 1.1.0 | LGPL-2.1-or-later |
| bidict | 0.23.1 | MPL 2.0 |
| certifi | 2026.5.20 | MPL-2.0 |
| intel-openmp | 2021.4.0 | Intel End User License Agreement for Developer Tools |
| mkl | 2021.4.0 | Intel Simplified Software License |
| tbb | 2021.13.1 | Intel Simplified Software License |

This is a representative record, not a complete package-by-package license list. The collected machine-readable inventory is an audit aid and is not committed as part of the application.

## FFmpeg

The local executable was identified as:

```text
ffmpeg version 7.1.1-full_build-www.gyan.dev
built with gcc 14.2.0
--enable-gpl
--enable-version3
--enable-static
```

The build configuration enables a broad set of external libraries, including x264, x265, libvpx, libaom, libass, libopus and libsoxr.

**Local executable SHA-256:**

```text
B1383F5D07470D503EDECDAEE4BDDC5891E986E916A698299B357F79CFE445FD
```

Gyan identifies its full static builds as GPLv3. The runtime contains `tools/LICENSE.GPL.txt`. The exact original Gyan archive and corresponding-source package for this binary have not been retained in the project audit, so this file does not claim that every GPL redistribution requirement has been independently verified. See [Gyan FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/) and the [FFmpeg legal page](https://ffmpeg.org/legal.html).

## Distribution note

The portable runtime is a bundle of independently licensed upstream components; it is not wholly covered by the Studio MIT License. The original `mortimerme/repocollect` Hugging Face repository used as the portable starting point contains the `cosyvoice3-0529.7z` archive but, at the time checked (2026-11-16), its top-level file list has no separate `LICENSE` or `THIRD_PARTY_NOTICES` file. This describes the upstream repository's documentation practice; it does **not** prove that the contents of the archive are license-free or that redistribution has no conditions.

This document is a lightweight reference for maintainers, not a complete SBOM or a legal audit. A package-by-package inventory of every transitive Python dependency is not a release requirement for this small, free, non-commercial local project. Keep the upstream license/notice files already supplied with the runtime and do not present third-party components as Studio's own work.

For personal use of the local Studio source/runtime, no separate redistribution checklist is needed. If the complete portable archive is copied or published for other people, the applicable third-party terms still matter even when the download is free. In particular, the included Gyan FFmpeg executable is identified as a GPLv3 build; distribution of that binary requires following the relevant GPLv3 conditions, including the corresponding-source requirements. NVIDIA CUDA/cuDNN and other bundled components remain subject to their own terms. This is a practical warning, not a claim that a full legal review has been completed.

## Source references

- [CosyVoice upstream](https://github.com/FunAudioLLM/CosyVoice)
- [Matcha-TTS upstream](https://github.com/shivammehta25/Matcha-TTS)
- [Fun-CosyVoice3-0.5B-2512 model card](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512)
- [Original portable base archive](https://huggingface.co/mortimerme/repocollect)
- [PyTorch 2.7.1](https://pypi.org/project/torch/2.7.1/)
- [Python license](https://docs.python.org/3/license.html)
- [Gyan FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/)
- [FFmpeg legal information](https://ffmpeg.org/legal.html)
