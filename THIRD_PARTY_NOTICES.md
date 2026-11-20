# Third-party notices and license inventory

**Status:** practical best-effort inventory of the main bundled components; not a legal opinion, exhaustive SBOM, or package-by-package compliance certification  
**Last reviewed:** 2026-11-20  
**Applies to:** Stream TTS Studio source repository and the portable runtime described in [docs/PORTABLE_RUNTIME.md](docs/PORTABLE_RUNTIME.md).

## Scope

The root [MIT License](LICENSE) applies to original Stream TTS Studio code and documentation. It does not relicense third-party components bundled with the portable distribution.

The portable runtime was inherited from the CosyVoice 3 portable setup and subsequently updated for this project. This inventory records the main known components and the information collected from the actual runtime. It does not attempt to enumerate every transitive Python package individually.

## Portable base and main components

| Component | Known version / source | License information | Notes |
|---|---|---|---|
| Stream TTS Studio original code | Current repository revision | MIT | See root `LICENSE` |
| Original portable base | [mortimerme/repocollect](https://huggingface.co/mortimerme/repocollect), `cosyvoice3-0529.7z` | Contains third-party components under their respective licenses | Identified in project README as the starting point of the portable setup |
| CosyVoice | CosyVoice 3; upstream [QwenAudio/CosyVoice](https://github.com/QwenAudio/CosyVoice) | Apache-2.0 | Upstream project license; upstream contains a separate `third_party` directory whose components retain their own licenses. Exact local submodule revisions/content were not fully matched |
| Matcha-TTS | Upstream dependency of CosyVoice; [shivammehta25/Matcha-TTS](https://github.com/shivammehta25/Matcha-TTS) | MIT | Separate upstream component; preserve its copyright/license notice when redistributing its code |
| Fun-CosyVoice3-0.5B-2512 | [Official model card](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512) | Apache-2.0 in repository metadata | Local folder uses the shortened name `Fun-CosyVoice3-0.5B`. Previously checked local `llm.pt` SHA-256 matches the official file hash; the remaining model files are not pinned as a whole to an immutable revision |
| faster-whisper-small | [Systran/faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small) | MIT in model repository metadata | Local model directory is present; exact local snapshot/hash was not pinned |
| Python | 3.10.11 | Python Software Foundation License | Portable interpreter; retain the license files supplied with the runtime |
| PyTorch | 2.7.1+cu128 | BSD-3-Clause | PyTorch distribution also contains notices/licenses for bundled components |
| CUDA / cuDNN | CUDA 12.8; cuDNN 9.7.1 in the recorded environment | NVIDIA license terms | NVIDIA components are subject to their own terms |
| FFmpeg | 7.1.1-full_build-www.gyan.dev | GPLv3 build | Exact local build details are recorded below |
| PyAV (`av`) | 17.1.0; PyPI binary wheel | BSD-3-Clause for PyAV binding; bundled FFmpeg 8.1.1 build is configured as GPLv3 | PyAV 17.1.0 release notes identify FFmpeg 8.1.1 in binary wheels. Its upstream build script enables GPL, version 3 and libx264. Local wheel provenance/binaries were not separately inspected; treat this as a likely additional GPLv3 payload for distribution planning |

## Model card clarification

The official model repository is marked `apache-2.0`. Its model card also contains a disclaimer stating that the card content is for academic purposes and that some examples are sourced from the internet. The disclaimer's scope over the model weights is not separately clarified in the card text inspected for this inventory. This document therefore records the repository's declared Apache-2.0 metadata without interpreting the disclaimer as either an additional weight restriction or a legal confirmation for every possible use. Recheck the upstream card if the distribution/use case changes materially.

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

## PyAV and its bundled FFmpeg

The local `pip freeze` snapshot includes `av==17.1.0`. PyAV's 17.1.0 release notes state that its binary wheels use FFmpeg 8.1.1, and its installation documentation confirms that the Windows/PyPI wheels are linked against FFmpeg libraries. The upstream v17.1.0 build script configures FFmpeg with `--enable-gpl`, `--enable-version3` and `--enable-libx264`. This points to an additional GPLv3 FFmpeg build inside the PyAV wheel, separate from the standalone Gyan `ffmpeg.exe`.

The PyAV Python binding itself is BSD-3-Clause, but that metadata does not replace the license of FFmpeg and codec libraries linked into its binary wheel. The exact origin of the local `av==17.1.0` installation and its DLL contents have not been independently inspected. For a conservative redistribution inventory, treat the official PyAV 17.1.0 wheel as containing GPLv3 FFmpeg 8.1.1 unless a local package inspection establishes otherwise.

Source trail: [PyAV v17.1.0 release](https://github.com/PyAV-Org/PyAV/releases/tag/v17.1.0), [PyAV FFmpeg build script](https://github.com/PyAV-Org/PyAV/blob/v17.1.0/scripts/build-deps), [PyAV FFmpeg source/release configuration](https://github.com/PyAV-Org/PyAV/blob/v17.1.0/scripts/ffmpeg-latest.json), [PyAV FFmpeg build project](https://github.com/PyAV-Org/pyav-ffmpeg/releases/tag/8.1.1-2), [FFmpeg 8.1.1 source archive](https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz).

## FFmpeg

The bundled executable was matched against the official Gyan 7.1.1 Full Build archive:

```text
Version: 7.1.1-full_build-www.gyan.dev
Build: Gyan Full Build, 64-bit static Windows
Archive: ffmpeg-7.1.1-full_build.zip
Archive SHA-256: D760E1B3574402ED18B4865851F87D87E73965A982E6453212DF8621FED1C508
FFmpeg source commit: db69d06eee
--enable-gpl
--enable-version3
--enable-static
```

The official archive was downloaded and inspected. Its SHA-256 matches the published archive checksum. The SHA-256 of the extracted `bin/ffmpeg.exe` also matches the executable in the local portable runtime:

```text
B1383F5D07470D503EDECDAEE4BDDC5891E986E916A698299B357F79CFE445FD
```

The archive's `README.txt` identifies the build as GPL v3 and records its configuration and a broad list of statically linked external libraries. The archive also contains a `LICENSE` file. The runtime contains `tools/LICENSE.GPL.txt`.

The official archive and executable identity are confirmed. Gyan subsequently supplied a dependency/build-toolchain manifest with repository URLs and commit hashes and confirmed by email that no functional patches were applied and that the standard build instructions in the respective dependency repositories are sufficient. The manifest is preserved verbatim in [licenses/ffmpeg/ffmpeg-7.1.1-full_build-manifest.txt](licenses/ffmpeg/ffmpeg-7.1.1-full_build-manifest.txt); the binary identity, maintainer clarification and source-retrieval notes are recorded in [licenses/ffmpeg/BUILD_INFO.md](licenses/ffmpeg/BUILD_INFO.md).

This is a materially stronger source trail than was previously available, but it is not an independently reproduced build. The manifest identifies source locations and revisions; it does not contain the source trees themselves, and this project has not yet independently fetched every pinned revision/package or verified the complete build-toolchain materials. The manifest also must not be read as proof that every listed dependency is linked into the FFmpeg executable. Gyan specifically cautioned that embedded strings naming a library do not establish that the library object is present. The full GPLv3 text is included in the repository at [`licenses/ffmpeg/COPYING.GPLv3`](licenses/ffmpeg/COPYING.GPLv3); the portable runtime also contains `cosyvoice3/tools/LICENSE.GPL.txt`. Retain the applicable GPLv3 license text alongside FFmpeg in redistributed packages.

References: [Gyan FFmpeg 7.1.1 release](https://github.com/GyanD/codexffmpeg/releases/tag/7.1.1), [Gyan FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/), [FFmpeg legal page](https://ffmpeg.org/legal.html), [GNU GPLv3 text](https://www.gnu.org/licenses/gpl-3.0.html).

## Distribution note

The portable runtime is a bundle of independently licensed upstream components; it is not wholly covered by the Studio MIT License. The original [mortimerme/repocollect](https://huggingface.co/mortimerme/repocollect) repository contains the `cosyvoice3-0529.7z` archive. Its top-level listing was previously checked and had no separate `LICENSE` or `THIRD_PARTY_NOTICES` file. The archive listing identifies a single portable bundle, not a license grant for all contents. This does **not** prove that the archive contents are license-free or that redistribution has no conditions.

This document is a lightweight reference for maintainers, not a complete SBOM or a legal audit. The owner supplied a current `pip freeze` snapshot from portable Python 3.10.11 on 2026-11-20. It confirms the installed package versions; the complete package list is intentionally not duplicated here, and transitive packages are not individually classified in this document. A package-by-package inventory of every transitive dependency is outside the agreed practical scope for this small local project. Keep the upstream license/notice files already supplied with the runtime and do not present third-party components as Studio's own work.

For personal use of the local Studio source/runtime, no separate redistribution checklist is needed. If the complete portable archive is copied or published for other people, the applicable third-party terms still matter even when the download is free. In particular, the included Gyan FFmpeg executable is identified as a GPLv3 build; distribution of that binary requires following the relevant GPLv3 conditions, including the corresponding-source requirements. NVIDIA CUDA/cuDNN and other bundled components remain subject to their own terms. This is a practical warning, not a claim that a full legal review has been completed.

## Source references

- [CosyVoice upstream](https://github.com/QwenAudio/CosyVoice)
- [Matcha-TTS upstream and MIT license](https://github.com/shivammehta25/Matcha-TTS)
- [Fun-CosyVoice3-0.5B-2512 model card](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512)
- [Original portable base archive](https://huggingface.co/mortimerme/repocollect)
- [PyTorch 2.7.1](https://pypi.org/project/torch/2.7.1/)
- [NVIDIA CUDA Toolkit EULA](https://docs.nvidia.com/cuda/eula/index.html)
- [NVIDIA cuDNN EULA](https://docs.nvidia.com/cudnn/reference/eula/)
- [Systran faster-whisper-small model](https://huggingface.co/Systran/faster-whisper-small)
- [PyAV 17.1.0 release](https://github.com/PyAV-Org/PyAV/releases/tag/v17.1.0)
- [Python 3.10 license and incorporated-software notices](https://docs.python.org/3.10/license.html)
- [Gyan FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/)
- [FFmpeg legal information](https://ffmpeg.org/legal.html)
