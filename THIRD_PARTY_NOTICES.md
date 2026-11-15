# Third-party notices and license inventory

**Status:** source-level inventory complete for identified components; portable-bundle compliance remains unverified  
**Last reviewed:** 2026-11-16  
**Applies to:** Stream TTS Studio source repository and the separately supplied portable runtime described in [docs/PORTABLE_RUNTIME.md](docs/PORTABLE_RUNTIME.md).

## Scope

The MIT License in the repository applies only to original Stream TTS Studio code and documentation authored for this project, unless a file says otherwise. It does not replace the license of third-party libraries, models, binaries, fonts, or other assets.

This file is an inventory of components currently known from the source tree and the owner's portable-runtime snapshot. It is not a complete Software Bill of Materials (SBOM), legal opinion, or proof that every redistribution obligation has been satisfied.

## Known components

| Component | Known version / revision | License information | Verification status |
|---|---|---|---|
| Stream TTS Studio original code | Current repository revision | MIT | See root `LICENSE`; applies only to original project work |
| CosyVoice upstream code | CosyVoice 3 | Apache License 2.0 | Upstream repository identifies Apache-2.0; exact vendored/runtime revision and all `third_party` contents still need comparison |
| Fun-CosyVoice3-0.5B-2512 | Model files under `pretrained_models/Fun-CosyVoice3-0.5B` | Apache-2.0 per official Hugging Face model card | License metadata verified; local snapshot not pinned to an immutable model revision as a whole. `llm.pt` SHA-256 was checked against the official file in the project diagnostics, but this does not pin all model files |
| PyTorch | 2.7.1+cu128 | PyPI metadata: BSD-3-Clause; wheel also contains license files for bundled third-party components | Top-level package metadata verified; wheel's bundled license files and CUDA/native dependencies must be retained and inventoried |
| Python | 3.10.11 portable | Python Software Foundation License | Runtime version identified; distribution files and notices should be retained |
| FFmpeg | 7.1.1, Gyan full static build | GPLv3, as stated by Gyan for its static builds | Build family and version recorded from local runtime snapshot; exact archive identity, SHA-256, build configuration, corresponding source and shipped GPL materials still missing |
| CUDA / cuDNN | CUDA build 12.8; cuDNN 9.7.1 in the owner's snapshot | NVIDIA proprietary license terms | Exact redistributable files and applicable NVIDIA license texts need inventory |
| Other Python packages and native dependencies | See version snapshot in `docs/PORTABLE_RUNTIME.md` | Varies by package | Incomplete; full package/dependency inventory and each license/NOTICE remain to be collected |
| Model auxiliaries, tokenizer/text-normalization assets, fonts and other runtime assets | Portable runtime folders | Varies by component | Not fully inventoried |

## Important FFmpeg note

The owner's snapshot identifies `ffmpeg.exe` as FFmpeg 7.1.1 from Gyan's **full** build. Gyan's build page states that its static builds are licensed under GPLv3. Before redistributing that binary, the distributor must identify the exact build/configuration and comply with the applicable GPLv3 obligations, including providing the required license text, notices and corresponding source or a valid means of obtaining it. Do not assume that the Studio MIT license covers FFmpeg.

The exact `ffmpeg -buildconf` output, binary SHA-256, original Gyan archive identity, corresponding source archive/revision and accompanying GPL materials were not included in the runtime snapshot. Therefore this repository does not yet claim that the FFmpeg redistribution checklist is complete.

## Provenance inherited from the portable base archive\n\nThe project README identifies `mortimerme/repocollect` (`cosyvoice3-0529.7z`) as the starting portable CosyVoice archive. That provenance is recorded, but the exact archive revision, its complete license set, and the licenses of files copied or modified from it have not been independently inventoried. The portable archive is outside Git; therefore this repository cannot claim complete licensing for it from source inspection alone. The archive must be unpacked and audited before its license status can be marked complete.\n\n## Required completion work before publishing a portable archive

1. Generate a complete inventory from the exact portable Python environment (direct and transitive Python packages, versions, license metadata); retain each package's bundled LICENSE/NOTICE files.
2. Inventory every bundled executable, DLL, native library, model, tokenizer, auxiliary model, font and asset under the portable runtime.
3. Record exact source URLs and immutable revisions/hashes for components where available.
4. Copy required LICENSE, NOTICE, attribution and other license texts into the distribution in the locations required by their licenses.
5. For FFmpeg, record `-version`, `-buildconf`, binary SHA-256, exact Gyan archive/build identity, relevant source and GPLv3 compliance materials. Gyan identifies its static builds as GPLv3; do not redistribute the binary without satisfying the applicable GPLv3 source and notice requirements.
6. Review NVIDIA CUDA/cuDNN redistribution terms for the exact files shipped.
7. Re-run the inventory whenever the portable archive or any included component changes.

## Source references

- [CosyVoice upstream repository](https://github.com/FunAudioLLM/CosyVoice) — Apache-2.0 project licensing; verify notices and submodules for the exact revision used.
- [Fun-CosyVoice3-0.5B-2512 model card](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512) — model-card metadata declares Apache-2.0.
- [PyTorch 2.7.1 on PyPI](https://pypi.org/project/torch/2.7.1/) — BSD-style license metadata.
- [Gyan FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/) — states static builds are GPLv3.
- [Python License](https://docs.python.org/3/license.html) — Python license text and terms.

**Distribution status:** the original Studio source license is identified. Known upstream licenses are documented. The complete license compliance of the portable distribution — including inherited base archive, all Python/native dependencies, models, FFmpeg and NVIDIA components — is **not yet verified**. Do not describe the complete portable archive as MIT-licensed.